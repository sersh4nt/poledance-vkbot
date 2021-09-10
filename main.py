from server import Server
from config import *

server = Server(TOKEN, GROUP_ID)
server.main_loop()
