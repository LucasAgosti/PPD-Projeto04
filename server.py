import socket
import threading
import pickle
import pika  # Biblioteca RabbitMQ
import time


class ChatServer:
    def __init__(self, host='192.168.0.11', port=22226, max_clients=10):
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.clients = {}  # Dicionário para armazenar conexões de clientes e seus nomes de usuário
        self.client_status = {}  # Dicionário para armazenar o status online/offline dos clientes
        self.private_chats = {}  # Dicionário para gerenciar conversas privadas
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.lock = threading.Lock()  # Lock para gerenciar o acesso às variáveis compartilhadas

        # Conectar ao RabbitMQ
        self.connect_rabbitmq()

    def connect_rabbitmq(self):
        """Tenta conectar ao RabbitMQ, com reconexão em caso de falha."""
        try:
            self.rabbitmq_connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            print("Conexão com RabbitMQ estabelecida.")
        except Exception as e:
            print(f"Erro ao conectar ao RabbitMQ: {e}. Tentando novamente em 5 segundos...")
            time.sleep(5)
            self.connect_rabbitmq()

    def start(self):
        print(f"Servidor iniciado em {self.host}:{self.port}")
        try:
            self.accept_connections()
        except Exception as e:
            print(f"Erro no servidor: {e}")
        finally:
            self.shutdown()

    def accept_connections(self):
        print("Aguardando conexões...")
        while True:
            try:
                client, addr = self.server_socket.accept()
                threading.Thread(target=self.register_client, args=(client,), daemon=True).start()
            except Exception as e:
                print(f"Erro ao aceitar conexões: {e}")
                break

    def register_client(self, client):
        try:
            username = pickle.loads(client.recv(4096))
            with self.lock:
                if username in self.clients.values():
                    client.send(pickle.dumps("Nome de usuário já em uso. Tente outro."))
                    client.close()
                    return
                self.clients[client] = username
                self.client_status[username] = True  # Inicialmente, todos os clientes estão online

                # Criar uma fila para o usuário no RabbitMQ, caso ela não exista ainda
                self.rabbitmq_channel.queue_declare(queue=username, durable=True)
            print(f"Usuário {username} conectado e fila de mensagens criada.")
            self.update_user_list()
            self.handle_client(client)
        except Exception as e:
            print(f"Erro ao registrar cliente: {e}")
            client.close()

    def handle_client(self, client):
        try:
            while True:
                data = client.recv(4096)
                if not data:
                    break
                action_data = pickle.loads(data)
                print(f"Ação recebida de {self.clients[client]}: {action_data}")
                self.handle_action(action_data, client)
        except Exception as e:
            print(f"Erro ao gerenciar cliente {self.clients[client]}: {e}")
        finally:
            with self.lock:
                username = self.clients.pop(client, None)
                self.client_status.pop(username, None)
                if username:
                    print(f"Usuário {username} desconectado.")
            client.close()
            self.update_user_list()

    def handle_action(self, action_data, client):
        if action_data['action'] == 'send_private_message':
            target_user = action_data['target_user']
            message = action_data['message']

            # Verificar se o destinatário está online
            if self.client_status.get(target_user, False):
                # Se o destinatário estiver online, enviar a mensagem diretamente
                self.send_private_message(client, message, target_user)
            else:
                # Se o destinatário estiver offline, enviar a mensagem para a fila do RabbitMQ e confirmar ao remetente
                self.send_message_to_queue(client, target_user, message)

        elif action_data['action'] == 'status_update':
            with self.lock:
                self.client_status[self.clients[client]] = action_data['status']
            print(f"{self.clients[client]} mudou para {'online' if action_data['status'] else 'offline'}")

            # Se o cliente ficar online, buscar mensagens offline
            if action_data['status']:
                threading.Thread(target=self.retrieve_offline_messages, args=(self.clients[client],)).start()

    def send_private_message(self, client, message, target_user):
        """Enviar mensagem diretamente para o cliente se estiver online."""
        target_client = next((c for c, u in self.clients.items() if u == target_user), None)
        if target_client:
            try:
                # Enviar mensagem privada ao destinatário
                target_client.send(pickle.dumps(f"{self.clients[client]} (privado): {message}"))
                # Confirmar ao remetente que a mensagem foi enviada, mas sem duplicação
                client.send(pickle.dumps(f"Você (privado): {message}"))
            except Exception as e:
                print(f"Erro ao enviar mensagem para {target_user}: {e}")
        else:
            print(f"Usuário {target_user} não encontrado online.")

    def send_message_to_queue(self, client, target_user, message):
        """Enviar mensagem para a fila do destinatário no RabbitMQ e confirmar para o remetente."""
        try:
            # Verificar se a conexão está ativa
            if self.rabbitmq_connection.is_closed:
                print("Conexão com RabbitMQ perdida. Tentando reconectar...")
                self.connect_rabbitmq()

            # Enviar mensagem para a fila do destinatário
            self.rabbitmq_channel.basic_publish(
                exchange='',
                routing_key=target_user,
                body=message,
                properties=pika.BasicProperties(delivery_mode=2)  # Tornar mensagem persistente
            )
            print(f"Mensagem para {target_user} armazenada na fila RabbitMQ.")

            # Confirmar ao remetente que a mensagem foi enviada
            client.send(pickle.dumps(f"Você (privado): {message}"))

        except Exception as e:
            print(f"Erro ao enviar mensagem para a fila do RabbitMQ: {e}")
            # Tentar reconectar ao RabbitMQ em caso de falha
            self.connect_rabbitmq()

    def retrieve_offline_messages(self, username):
        """Buscar mensagens offline da fila do RabbitMQ e enviar ao cliente."""
        try:
            # Verificar se a conexão está ativa antes de consumir
            if self.rabbitmq_connection.is_closed:
                print("Conexão com RabbitMQ perdida. Tentando reconectar...")
                self.connect_rabbitmq()

            messages = []
            while True:
                method_frame, properties, body = self.rabbitmq_channel.basic_get(queue=username, auto_ack=False)
                if method_frame:
                    messages.append(body.decode())
                    self.rabbitmq_channel.basic_ack(method_frame.delivery_tag)
                else:
                    break

            if messages:
                print(f"Entregando {len(messages)} mensagens offline para {username}")
                # Enviar todas as mensagens offline como uma lista
                self.send_private_message_direct(username, messages)

        except Exception as e:
            print(f"Erro ao consumir mensagens offline para {username}: {e}")
            # Recriar a conexão RabbitMQ em caso de erro
            self.connect_rabbitmq()

    def send_private_message_direct(self, username, messages):
        """Enviar lista de mensagens offline diretamente para o cliente."""
        target_client = next((c for c, u in self.clients.items() if u == username), None)
        if target_client:
            try:
                # Enviar a lista de mensagens como um objeto serializado
                target_client.send(pickle.dumps(messages))
            except Exception as e:
                print(f"Erro ao enviar mensagens para {username}: {e}")

    def update_user_list(self):
        with self.lock:
            user_list = list(self.clients.values())
            for client in self.clients.keys():
                try:
                    client.send(pickle.dumps({'action': 'update_user_list', 'user_list': user_list}))
                except Exception as e:
                    print(f"Erro ao enviar lista de usuários para {self.clients[client]}: {e}")

    def shutdown(self):
        print("Encerrando o servidor...")
        with self.lock:
            for client in self.clients.keys():
                client.close()
            self.server_socket.close()
            self.rabbitmq_connection.close()


if __name__ == '__main__':
    server = ChatServer()
    server.start()
