import socket
import threading
import pickle


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

        # Adicionado: Servidor de mensagens offline
        self.offline_server_host = '192.168.0.11'  # IP do servidor de mensagens offline
        self.offline_server_port = 22227  # Porta do servidor de mensagens offline

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
                self.client_status[client] = True  # Inicialmente, todos os clientes estão online
            print(f"Usuário {username} conectado.")
            self.update_user_list()
            self.handle_client(client)
        except Exception as e:
            print(f"Erro ao registrar cliente: {e}")
            client.close()

    def handle_client(self, client):
        try:
            username = self.clients[client]
            # Verificar se o cliente tem mensagens pendentes ao se conectar
            pending_messages = self.get_offline_messages(username)
            if pending_messages:
                for msg in pending_messages:
                    client.send(pickle.dumps(msg))
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
                self.client_status.pop(client, None)
                if username:
                    print(f"Usuário {username} desconectado.")
            client.close()
            self.update_user_list()

    def handle_action(self, action_data, client):
        if action_data['action'] == 'start_private_chat':
            self.start_private_chat(client, action_data['target_user'])
        elif action_data['action'] == 'send_private_message':
            self.send_private_message(client, action_data['message'], action_data['target_user'])
        elif action_data['action'] == 'status_update':
            with self.lock:
                self.client_status[client] = action_data['status']
            print(f"{self.clients[client]} mudou para {'online' if action_data['status'] else 'offline'}")

    def start_private_chat(self, client, target_user):
        with self.lock:
            target_client = next((c for c, u in self.clients.items() if u == target_user), None)
            if target_client:
                chat_id = frozenset([self.clients[client], target_user])
                self.private_chats[chat_id] = (client, target_client)
                client.send(pickle.dumps(f"Iniciado chat privado com {target_user}."))
                target_client.send(pickle.dumps(f"{self.clients[client]} iniciou um chat privado com você."))
            else:
                client.send(pickle.dumps(f"Usuário {target_user} não encontrado."))

    def send_private_message(self, client, message, target_user):
        chat_id = frozenset([self.clients[client], target_user])
        target_client = next((c for c, u in self.clients.items() if u == target_user), None)

        if chat_id in self.private_chats:
            if not self.client_status.get(target_client, False):
                # Se o cliente alvo estiver offline, envia a mensagem ao servidor de mensagens offline
                self.send_to_offline_server(target_user, f"{self.clients[client]} (privado): {message}")
                client.send(pickle.dumps(f"{target_user} está offline. Mensagem enviada para armazenamento."))
            else:
                # Envia a mensagem diretamente se o alvo estiver online
                client_a, client_b = self.private_chats[chat_id]
                if client == client_a and self.client_status[client_b]:
                    client_b.send(pickle.dumps(f"{self.clients[client]} (privado): {message}"))
                elif client == client_b and self.client_status[client_a]:
                    client_a.send(pickle.dumps(f"{self.clients[client]} (privado): {message}"))
        else:
            client.send(pickle.dumps(f"Chat privado com {target_user} não encontrado."))

    def send_to_offline_server(self, target_user, message):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as offline_socket:
                offline_socket.connect((self.offline_server_host, self.offline_server_port))
                request = {'action': 'store_message', 'target_user': target_user, 'message': message}
                offline_socket.send(pickle.dumps(request))
        except Exception as e:
            print(f"Erro ao enviar mensagem para o servidor offline: {e}")

    def get_offline_messages(self, username):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as offline_socket:
                offline_socket.connect((self.offline_server_host, self.offline_server_port))
                request = {'action': 'get_messages', 'target_user': username}
                offline_socket.send(pickle.dumps(request))
                data = offline_socket.recv(4096)
                messages = pickle.loads(data)
                return messages
        except Exception as e:
            print(f"Erro ao buscar mensagens offline: {e}")
            return []

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


if __name__ == '__main__':
    server = ChatServer()
    server.start()
