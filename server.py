import socket
import threading
import pickle

class ChatServer:
    def __init__(self, host='192.168.0.11', port=22226, max_clients=10):
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.clients = []  # Lista para armazenar conexões de clientes
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.rooms = {}  # Dicionário para gerenciar as salas de chat
        self.lock = threading.Lock()  # Lock para gerenciar o acesso às variáveis compartilhadas

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
                print(f"Conexão recebida de {addr}")
                with self.lock:
                    self.clients.append(client)
                threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()
            except Exception as e:
                print(f"Erro ao aceitar conexões: {e}")
                break

    def handle_client(self, client):
        try:
            client.send(pickle.dumps("Bem-vindo ao servidor de chat!"))
            self.client_actions(client)
        except Exception as e:
            print(f"Erro ao gerenciar cliente: {e}")
        finally:
            with self.lock:
                self.clients.remove(client)
            client.close()

    def client_actions(self, client):
        while True:
            try:
                data = client.recv(4096)
                if not data:
                    break
                action_data = pickle.loads(data)
                print(f"Ação recebida: {action_data}")
                self.handle_action(action_data, client)
            except Exception as e:
                print(f"Erro ao receber dados do cliente: {e}")
                break

    def handle_action(self, action_data, client):
        if action_data['action'] == 'create_room':
            self.create_room(action_data['room_name'], client)
        elif action_data['action'] == 'join_room':
            self.join_room(action_data['room_name'], client)
        elif action_data['action'] == 'send_message':
            self.send_message(action_data['room_name'], action_data['message'], client)
        elif action_data['action'] == 'leave_room':
            self.leave_room(action_data['room_name'], client)

    def create_room(self, room_name, client):
        with self.lock:
            if room_name not in self.rooms:
                self.rooms[room_name] = [client]
                client.send(pickle.dumps(f"Sala '{room_name}' criada e você entrou nela."))
            else:
                client.send(pickle.dumps(f"Sala '{room_name}' já existe. Use outro nome."))

    def join_room(self, room_name, client):
        with self.lock:
            if room_name in self.rooms:
                self.rooms[room_name].append(client)
                client.send(pickle.dumps(f"Você entrou na sala '{room_name}'."))
            else:
                client.send(pickle.dumps(f"Sala '{room_name}' não existe. Crie uma nova sala ou escolha outra."))

    def leave_room(self, room_name, client):
        with self.lock:
            if room_name in self.rooms and client in self.rooms[room_name]:
                self.rooms[room_name].remove(client)
                client.send(pickle.dumps(f"Você saiu da sala '{room_name}'."))
                if len(self.rooms[room_name]) == 0:
                    del self.rooms[room_name]
                    print(f"Sala '{room_name}' foi excluída por estar vazia.")
            else:
                client.send(pickle.dumps(f"Você não está na sala '{room_name}'."))

    def send_message(self, room_name, message, client):
        with self.lock:
            if room_name in self.rooms:
                for user in self.rooms[room_name]:
                    if user != client:
                        user.send(pickle.dumps(message))

    def shutdown(self):
        print("Encerrando o servidor...")
        with self.lock:
            for client in self.clients:
                client.close()
            self.server_socket.close()

if __name__ == '__main__':
    server = ChatServer()
    server.start()
