import tkinter as tk
from tkinter import simpledialog
import socket
import threading
import pickle


class ChatClient(tk.Tk):
    def __init__(self):
        super().__init__()
        self.username = None
        self.client_socket = None
        self.connected = False
        self.current_chat_user = None  # Armazena o usuário com quem o cliente está conversando
        self.is_online = True  # Atributo para armazenar o estado online/offline
        self.setup_chat_interface()

    def setup_chat_interface(self):
        self.chat_log = tk.Text(self, state='disabled', width=50, height=15)
        self.chat_log.grid(row=0, column=0, columnspan=2, sticky="nsew")

        self.chat_message = tk.Entry(self, width=50)
        self.chat_message.grid(row=2, column=0, sticky="ew")

        send_button = tk.Button(self, text="Enviar", command=self.send_chat_message)
        send_button.grid(row=2, column=1, sticky="ew")

        self.user_list = tk.Listbox(self, width=30, height=15)
        self.user_list.grid(row=0, column=2, rowspan=3, sticky="nsw")
        self.user_list.bind('<<ListboxSelect>>', self.on_user_select)

        # Botão para alternar entre online e offline
        self.toggle_button = tk.Button(self, text="Ficar Offline", command=self.toggle_online_status)
        self.toggle_button.grid(row=3, column=0, columnspan=3, sticky="ew")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def toggle_online_status(self):
        self.is_online = not self.is_online
        if self.is_online:
            self.toggle_button.config(text="Ficar Offline")
            self.update_chat_log("Você está online.")
            self.update_server_online_status(True)
        else:
            self.toggle_button.config(text="Ficar Online")
            self.update_chat_log("Você está offline.")
            self.update_server_online_status(False)

    def update_server_online_status(self, status):
        if self.connected:
            try:
                message = {"action": "status_update", "status": status}
                self.client_socket.send(pickle.dumps(message))
            except Exception as e:
                print(f"Erro ao atualizar status: {e}")

    def connect_to_server(self, host='192.168.0.11', port=22226):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client_socket.connect((host, port))
            self.connected = True
            self.request_username()
            self.check_for_incoming_data()
        except Exception as e:
            print(f"Erro ao conectar ao servidor: {e}")

    def request_username(self):
        self.username = simpledialog.askstring("Nome de Usuário", "Digite seu nome de usuário:")
        if self.username:
            self.title(f"Perfil do {self.username}")  # Define o título da janela com o nome do cliente
            self.client_socket.send(pickle.dumps(self.username))

    def check_for_incoming_data(self):
        if self.connected:
            try:
                self.client_socket.settimeout(0.1)
                while True:  # Processar várias mensagens de uma vez
                    try:
                        data = self.client_socket.recv(4096)
                        if data:
                            messages = pickle.loads(data)

                            # Verifica se é uma lista de mensagens
                            if isinstance(messages, list):
                                for message in messages:
                                    self.update_chat_log(message)
                            elif isinstance(messages, str):
                                # Caso a mensagem seja uma string, exiba normalmente
                                self.update_chat_log(messages)
                            elif isinstance(messages, dict):
                                # Se for um dict (como o update de lista de usuários)
                                if 'user_list' in messages:
                                    self.update_user_list(messages['user_list'])
                    except socket.timeout:
                        break
            except Exception as e:
                print(f"Erro ao receber dados: {e}")
                self.connected = False
            self.after(100, self.check_for_incoming_data)

    def update_chat_log(self, message):
        self.chat_log.config(state='normal')
        self.chat_log.insert(tk.END, message + '\n')  # Adicionando uma nova linha após cada mensagem
        self.chat_log.config(state='disabled')
        self.chat_log.see(tk.END)

    def update_user_list(self, user_list):
        self.user_list.delete(0, tk.END)
        for user in user_list:
            if user != self.username:
                self.user_list.insert(tk.END, user)

    def on_user_select(self, event):
        selected_user = self.user_list.get(self.user_list.curselection())
        if selected_user and selected_user != self.current_chat_user:
            self.current_chat_user = selected_user
            self.start_private_chat(selected_user)

    def start_private_chat(self, target_user):
        if target_user:
            start_chat_message = {'action': 'start_private_chat', 'target_user': target_user}
            self.send_data_to_server(start_chat_message)
            self.update_chat_log(f"Iniciado chat privado com {target_user}")

    def send_chat_message(self):
        if not self.is_online:
            self.update_chat_log("Você está offline. Não é possível enviar mensagens.")
            return

        message = self.chat_message.get()
        if message and self.current_chat_user:
            formatted_message = {'action': 'send_private_message', 'message': message,
                                 'target_user': self.current_chat_user}
            self.send_data_to_server(formatted_message)
            self.chat_message.delete(0, tk.END)

    def send_data_to_server(self, data):
        try:
            self.client_socket.send(pickle.dumps(data))
        except Exception as e:
            print(f"Erro ao enviar dados: {e}")

    def run(self):
        self.mainloop()


if __name__ == "__main__":
    client = ChatClient()
    client.connect_to_server()
    client.run()
