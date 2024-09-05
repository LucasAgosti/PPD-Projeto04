import socket
import threading
import pickle

class OfflineMessageServer:
    def __init__(self, host='192.168.0.11', port=22227):
        self.host = host
        self.port = port
        self.messages = {}  # Dicionário para armazenar mensagens offline por cliente
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Servidor de mensagens offline iniciado em {self.host}:{self.port}")
        self.lock = threading.Lock()

    def start(self):
        while True:
            client, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()

    def handle_client(self, client):
        try:
            data = client.recv(4096)
            if data:
                request = pickle.loads(data)
                if request['action'] == 'store_message':
                    self.store_message(request['target_user'], request['message'])
                elif request['action'] == 'get_messages':
                    messages = self.get_messages(request['target_user'])
                    client.send(pickle.dumps(messages))
        except Exception as e:
            print(f"Erro no servidor offline: {e}")
        finally:
            client.close()

    def store_message(self, target_user, message):
        with self.lock:
            if target_user not in self.messages:
                self.messages[target_user] = []
            self.messages[target_user].append(message)
            print(f"Mensagem armazenada para {target_user}: {message}")

    def get_messages(self, target_user):
        with self.lock:
            messages = self.messages.pop(target_user, [])
            return messages

if __name__ == '__main__':
    offline_server = OfflineMessageServer()
    offline_server.start()
