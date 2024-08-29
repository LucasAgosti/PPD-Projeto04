import tkinter as tk
import socket
import threading
import pickle

class ChatClient(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Chat Client')
        self.setup_chat_interface()
        self.client_socket = None

    def setup_chat_interface(self):
        self.chat_log = tk.Text(self, state='disabled', width=50, height=15)
        self.chat_log.grid(row=0, column=0, columnspan=2, sticky="nsew")

        self.chat_message = tk.Entry(self, width=50)
        self.chat_message.grid(row=1, column=0, sticky="ew")

        send_button = tk.Button(self, text="Enviar", command=self.send_chat_message)
        send_button.grid(row=1, column=1, sticky="ew")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def connect_to_server(self, host='192.168.0.11', port=22226):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client_socket.connect((host, port))
            threading.Thread(target=self.receive_data_from_server, daemon=True).start()
        except Exception as e:
            print(f"Erro ao conectar ao servidor: {e}")

    def receive_data_from_server(self):
        while True:
            try:
                data = self.client_socket.recv(4096)
                if data:
                    message = pickle.loads(data)
                    self.update_chat_log(message)
            except Exception as e:
                print(f"Erro ao receber dados: {e}")
                break

    def update_chat_log(self, message):
        self.chat_log.config(state='normal')
        self.chat_log.insert(tk.END, message + '\n')
        self.chat_log.config(state='disabled')
        self.chat_log.see(tk.END)

    def send_chat_message(self):
        message = self.chat_message.get()
        if message:
            formatted_message = {'action': 'chat', 'message': message}
            self.send_data_to_server(formatted_message)
            self.update_chat_log("Você: " + message)
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
