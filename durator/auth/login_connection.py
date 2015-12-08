import time
import threading

from durator.auth.constants import LoginOpCodes
from durator.auth.login_challenge import LoginChallenge
from durator.auth.login_connection_state import LoginConnectionState
from durator.auth.login_proof import LoginProof
from durator.auth.recon_challenge import ReconChallenge
from durator.auth.recon_proof import ReconProof
from durator.auth.srp import Srp
from pyshgck.format import dump_data
from pyshgck.logger import LOG


class LoginConnection(object):
    """ Handle the login process of a client with a SRP challenge. """

    LEGAL_OPS = {
        LoginConnectionState.INIT:        [ LoginOpCodes.LOGIN_CHALL
                                          , LoginOpCodes.RECON_CHALL ],
        LoginConnectionState.CLOSED:      [ ],
        LoginConnectionState.SENT_CHALL:  [ LoginOpCodes.LOGIN_PROOF ],
        LoginConnectionState.SENT_PROOF:  [ LoginOpCodes.REALMLIST ],
        LoginConnectionState.RECON_CHALL: [ LoginOpCodes.RECON_PROOF ],
        LoginConnectionState.RECON_PROOF: [ LoginOpCodes.REALMLIST ],
    }

    OP_HANDLERS = {
        LoginOpCodes.LOGIN_CHALL: LoginChallenge,
        LoginOpCodes.LOGIN_PROOF: LoginProof,
        LoginOpCodes.RECON_CHALL: ReconChallenge,
        LoginOpCodes.RECON_PROOF: ReconProof
    }

    def __init__(self, server, connection, address):
        self.server = server
        self.socket = connection
        self.address = address
        self.state = LoginConnectionState.INIT
        self.account = None
        self.srp = Srp()
        self.recon_challenge = b""

    def __del__(self):
        self.socket.close()

    def is_opcode_legal(self, opcode):
        """ Check if that opcode is legal for the current connection state. """
        return opcode in LoginConnection.LEGAL_OPS[self.state]

    def close_connection(self):
        """ Close connection with client. """
        self.state = LoginConnectionState.CLOSED
        self.socket.close()
        LOG.debug("Server closed the connection.")

    def handle_connection(self):
        while self.state != LoginConnectionState.CLOSED:
            data = self.socket.recv(1024)
            if not data:
                LOG.debug("Client closed the connection.")
                break
            self._try_handle_packet(data)

    def _try_handle_packet(self, data):
        try:
            self._handle_packet(data)
        except Exception:
            LOG.error("Unhandled exception in LoginConnection._handle_packet")
            raise

    def _handle_packet(self, data):
        print("<<<")
        print(dump_data(data), end = "")

        opcode, packet = LoginOpCodes(data[0]), data[1:]
        if not self.is_opcode_legal(opcode):
            LOG.warning( "Received illegal opcode " + str(opcode)
                       + " in state " + str(self.state) )
            self.close_connection()
            return

        handler_class = LoginConnection.OP_HANDLERS.get(opcode)
        if handler_class is None:
            LOG.warning("Unknown operation: " + str(opcode))
            self.close_connection()
            return

        self._call_handler(handler_class, packet)

    def _call_handler(self, handler_class, packet):
        handler = handler_class(self, packet)
        next_state, response = handler.process()

        if response:
            print(">>>")
            print(dump_data(response), end = "")
            time.sleep(0.1)
            self.socket.sendall(response)

        if next_state is not None:
            self.state = next_state
        if self.state == LoginConnectionState.CLOSED:
            self.close_connection()

    def accept_login(self):
        session_key = self.srp.session_key
        self.server.accept_account_login(self.account, session_key)