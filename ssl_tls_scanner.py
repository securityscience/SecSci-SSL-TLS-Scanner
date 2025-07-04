# ---------------------------------------
# Sec-Sci SSL/TLS Scanner v3.0.250628 - June 2025
# ---------------------------------------
# Tool:      Sec-Sci SSL/TLS Scanner v3.0.250628
# Site:      www.security-science.com
# Email:     RnD@security-science.com
# Creator:   ARNEL C. REYES
# @license:  GNU GPL 3.0
# @copyright (C) 2025 WWW.SECURITY-SCIENCE.COM

from burp import IBurpExtender, IHttpListener, IScanIssue, IContextMenuFactory
from javax.swing import JMenuItem, JOptionPane
from java.util import ArrayList
from java.awt.event import ActionListener
from datetime import datetime
import subprocess, threading, json, urllib2, os, re

hosts = []
# ssl_scanner = ""


def is_sslscan_installed():
    try:
        output = subprocess.check_output(["sslscan", "--no-colour", "--version"], stderr=subprocess.STDOUT)
        print("[INFO] SSLScan version: {}".format(output.strip()))
        return True
    except OSError:
        return False
    except subprocess.CalledProcessError:
        return True

def is_nmap_installed():
    try:
        output = subprocess.check_output(["nmap", "--version"], stderr=subprocess.STDOUT)
        print("[INFO] NMap version: {}".format(output.strip()))
        return True
    except OSError:
        return False
    except subprocess.CalledProcessError:
        return True


def fetch_latest_issues(remote_ssl_issues_url):
    try:
        request = urllib2.Request(remote_ssl_issues_url)
        response = urllib2.urlopen(request, timeout=5)
        content = response.read()
        data = json.loads(content)
        local_file = "ssl_issues.json"

        # Write the new SSL Issues list to local file
        with open(local_file, 'w') as f:
            json.dump(data, f, indent=4)

        print("[INFO] Updated SSL Issues!")
        return data
    except Exception as e:
        print("[INFO] Failed to update SSL Issues from Remote: %s" % str(e))


def load_ssl_issues(local_file="ssl_issues.json"):
    if os.path.exists(local_file):
        try:
            with open(local_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print("[ERROR] Failed to load local issues file: %s" % str(e))
    return []  # Fallback to empty list if both remote and local fail


def run_sslscan(host, port, httpService, request_url, messageInfo, callbacks, scanner):
    if scanner == "sslscan":
        sslscan_cmd = ["sslscan", "--no-colour", "--iana-names", "--show-sigs", "--show-certificate", host + ":" + str(port)]
    else:
        sslscan_cmd = ["nmap", "-sV", "--script", "ssl*,tls*", "-p", str(port), host]

    # print("[INFO] Running SSLScan command: {}".format(sslscan_cmd))

    try:
        print("[!] SSL Scan Started for " + host + ":" + str(port))
        sslscan_output = subprocess.check_output(sslscan_cmd, stderr=subprocess.STDOUT)
        sslscan_output = sslscan_output.decode("utf-8")
        # print("[DEBUG] SSLScan output:\n" + sslscan_output)
    except subprocess.TimeoutExpired:
        print("[ERROR] SSLScan timed out")
        return None
    except Exception as e:
        print("[ERROR] SSLScan failed: {}".format(e))
        return None

    ssl_tls_issues = []
    ssl_issues = load_ssl_issues()
    burp_issue_severity = "Medium"

    insecure_certs = ssl_issues["Insecure_Certs"]
    insecure_cert_issues = ["<b>Insecure Certificate:</b><ul>"]

    for insecure_cert in insecure_certs:
        pattern = insecure_cert[0]
        description = insecure_cert[1]
        cert_severity = insecure_cert[2]
        condition = insecure_cert[3] if len(insecure_cert) > 3 else ""

        match_pattern = re.search(pattern, sslscan_output)

        if match_pattern:
            match_value = match_pattern.group(1)
            description_value = match_pattern.group(0)
            if burp_issue_severity not in ["Critical", "High"] and cert_severity in ["Critical", "High"]:
                burp_issue_severity = "High"

            #if isinstance(condition, basestring):
            if any(op in condition for op in ['<', '>', '=', '!=']):
                try:
                    # Condition is a numeric comparison string
                    if eval("%s%s" % (match_value, condition)):
                        insecure_cert_issues.append("<li>{0}: <b>{1}</b></li>".format(description, description_value))
                except:
                    pass
            elif 'datetime' in condition:
                try:
                    if scanner == "sslscan":
                        match_value = datetime.strptime(match_value.strip(), "%b %d %H:%M:%S %Y GMT")
                        match_value.strftime("%Y-%m-%dT%H:%M:%S")
                    else:
                        match_value = datetime.strptime(match_value.strip(), "%Y-%m-%dT%H:%M:%S")
                    # Condition is a datetime comparison string
                    if match_value < datetime.utcnow():
                        insecure_cert_issues.append("<li>{0}: <b>{1}</b></li>".format(description, description_value))
                except:
                    pass
            else:
                try:
                    # Condition is a regular string
                    if condition in match_value:
                        insecure_cert_issues.append("<li>{0}: <b>{1}</b></li>".format(description, description_value))
                except:
                    pass
    insecure_cert_issues.append("</ul>")

    if len(insecure_cert_issues) > 2:
        ssl_tls_issues = ssl_tls_issues + insecure_cert_issues

    deprecated_protocols = ssl_issues["Deprecated_Protocols"]
    deprecated_protocol_issues = ["<br><b>Deprecated Protocols Detected:</b><ul>"]

    for deprecated_protocol in deprecated_protocols:
        if deprecated_protocol[0] in sslscan_output:
            deprecated_protocol_issues.append('<li>{0}: <b>{1}</b></li>'.format(deprecated_protocol[0][:-1], deprecated_protocol[1]))
    deprecated_protocol_issues.append("</ul>")

    if len(deprecated_protocol_issues) > 2:
        ssl_tls_issues = ssl_tls_issues + deprecated_protocol_issues
        burp_issue_severity = "High"

    common_weak_ciphers = ssl_issues["Common_Weak_Ciphers"]
    common_weak_cipher_issues = ["<br><b>Common Weak Ciphers:</b><ul>"]

    for common_weak_cipher in common_weak_ciphers:
        if common_weak_cipher[0] in sslscan_output:
            common_weak_cipher_issues.append(
                '<li>{0}: '.format(common_weak_cipher[1]) + "<b>Yes</b></li>")
        else:
            common_weak_cipher_issues.append(
                '<li>{0}: '.format(common_weak_cipher[1]) + "<b>No</b></li>")
    common_weak_cipher_issues.append("</ul>")

    if len(common_weak_cipher_issues) > 2:
        ssl_tls_issues = ssl_tls_issues + common_weak_cipher_issues

    known_vulnerabilities = ssl_issues["Known_Vulnerabilities"]
    known_vulnerability_issues = ["<br><b>Known Vulnerabilities:</b><ul>"]

    for known_vulnerability in known_vulnerabilities:
        if known_vulnerability[0] in sslscan_output:
            known_vulnerability_issues.append(
                '<li>{0}: '.format(known_vulnerability[1]) + "<b>Yes</b></li>")
        else:
            known_vulnerability_issues.append(
                '<li>{0}: '.format(known_vulnerability[1]) + "<b>No</b></li>")
    known_vulnerability_issues.append("</ul>")

    if len(known_vulnerability_issues) > 2:
        ssl_tls_issues = ssl_tls_issues + known_vulnerability_issues

    insecure_ciphers = ssl_issues["Insecure_Ciphers"]
    insecure_cipher_issues = ["<br><b>Insecure Ciphers:</b><ul>"]

    for insecure_cipher in insecure_ciphers:
        if insecure_cipher[0] in sslscan_output:
            insecure_cipher_issues.append('<li><a href="https://ciphersuite.info/cs/TLS_{0}">TLS_{0}</a>: <b>{1}</b></li>'
                                          .format(insecure_cipher[0], insecure_cipher[1]))
    insecure_cipher_issues.append("</ul>")

    if len(insecure_cipher_issues) > 2:
        ssl_tls_issues = ssl_tls_issues + insecure_cipher_issues
        burp_issue_severity = "High"

    weak_ciphers = ssl_issues["Weak_Ciphers"]
    weak_cipher_issues = ["<br><b>Weak Ciphers:</b><ul>"]

    for weak_cipher in weak_ciphers:

        if weak_cipher[0] in sslscan_output:
            weak_cipher_issues.append('<li><a href="https://ciphersuite.info/cs/TLS_{0}">TLS_{0}</a>: <b>{1}</b></li>'
                                      .format(weak_cipher[0], weak_cipher[1]))
    weak_cipher_issues.append("</ul>")

    if len(weak_cipher_issues) > 2:
        ssl_tls_issues = ssl_tls_issues + weak_cipher_issues

    if ssl_tls_issues:
        issue_detail = """
        The server is configured to support weak SSL/TLS cipher suites, which could allow an attacker to decrypt 
        or tamper with encrypted traffic through methods such as cryptographic downgrade attacks, brute force,
        or protocol vulnerabilities.<br><br>
        During SSL/TLS negotiation with the server, the following weak cipher suites were found to be supported
        and indication of weak certificate:<br><br>
        """ + "".join(ssl_tls_issues) + """<br>
        Use of these cipher suites significantly reduces the strength of encryption and may expose sensitive
        data to interception or modification. SSL Scanner initiated a TLS handshake and observed these weak
        ciphers in the server's response. This indicates the server is not enforcing modern, secure cipher policies.
        <br><br><pre>""" + sslscan_output + """</pre><br>
        <br><b>Issue background</b><br><br>
        Cipher suites determine how TLS encryption is applied between the client and the server.
        Older or weak cipher suites use outdated algorithms (e.g., RC4, 3DES, MD5, NULL) that are considered
        insecure due to vulnerabilities or insufficient key lengths.<br><br>
        Attackers may exploit these weak ciphers to:
        <ul><li>Perform downgrade attacks (e.g., forcing use of export-grade or legacy ciphers)</li>
        <li>Exploit specific vulnerabilities like SWEET32, FREAK, or LOGJAM</li>
        <li>Break confidentiality or integrity of communications</li></ul>
        Modern TLS configurations should use only strong ciphers with forward secrecy and authenticated encryption,
        such as those based on AES-GCM or ChaCha20-Poly1305.<br><br>
        <br><b>Issue remediation</b><br><br>
        Reconfigure the web server to:
        <ul><li>Disable all weak, deprecated, or export-grade cipher suites</li>
        <li>Enable only secure cipher suites that offer forward secrecy (e.g., ECDHE with AES-GCM)</li>
        <li>Prefer TLS 1.2 and 1.3; disable SSL 2.0, SSL 3.0, TLS 1.0, and TLS 1.1</li></ul>
        Ensure the final configuration is tested using tools such as:
        <ul><li><a href="https://www.ssllabs.com/ssltest/">SSL Labs SSL Test</a></li>
        <li><a href="https://nmap.org/nsedoc/scripts/ssl-enum-ciphers.html">nmap --script ssl-enum-ciphers</a></li>
        <li><a href="https://nmap.org/nsedoc/scripts/ssl-cert.html">nmap --script ssl-cert</a></li>
        <li><a href="https://github.com/securityscience/sslscan">sslscan</a></li></ul><br>                    
        <br><b>References</b>
        <ul><li><a href="https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html">
        OWASP: Transport Layer Protection Cheat Sheet</a></li>
        <li><a href="https://www.ssllabs.com/ssltest/">SSL Labs: SSL Server Test</a></li>
        <li><a href="https://ssl-config.mozilla.org/">Mozilla SSL Configuration Generator</a></li>
        <li><a href="https://datatracker.ietf.org/doc/html/rfc7525">RFC 7525: Recommendations for Secure Use of TLS</a></li></ul><br>
        <br><b>Vulnerability classifications</b>
        <ul><li><a href="https://cwe.mitre.org/data/definitions/326.html">CWE-326: Inadequate Encryption Strength</a></li>
        <li><a href="https://cwe.mitre.org/data/definitions/327.html">CWE-327: Use of a Broken or Risky Cryptographic Algorithm</a></li>
        <li><a href="https://capec.mitre.org/data/definitions/242.html">CAPEC-242: Algorithm Downgrade Attack</a></li>
        <li><a href="https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2016-2183">CVE-2016-2183 (SWEET32)</a></li>
        <li><a href="https://www.first.org/cvss/calculator/3.1">CVSS v3.1 Calculator</a></li></ul>
        """

        issue = SSLScanIssue(
            httpService,
            request_url,
            [messageInfo],
            "[SecSci SSL/TLS Scan] Insecure Configuration",
            issue_detail,
            burp_issue_severity
        )
        callbacks.addScanIssue(issue)

        print("[!] SSL Scan Completed for " + host + ":" + str(port))


class BurpExtender(IBurpExtender, IHttpListener, IContextMenuFactory):

    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._ssl_scanner = ""
        callbacks.setExtensionName("SecSci SSL/TLS Scanner")
        callbacks.registerHttpListener(self)
        callbacks.registerContextMenuFactory(self)

        # if not is_nmap_installed():
        self._sslscan_installed = is_sslscan_installed()
        self._nmap_installed = is_nmap_installed()
        if not self._sslscan_installed and not self._nmap_installed:
            print("[ERROR] Unable to locate SSLScan or NMap.")
            print("[INFO] Check SSLScan or NMap installation directory and add to PATH environment variable.")
            return None

        self._ssl_scanner = "sslscan" if self._sslscan_installed else "nmap"

        print("[*] SSL/TLS Scanner extension loaded.")

        remote_ssl_issues_url = "https://raw.githubusercontent.com/securityscience/SecSci-SSL-TLS-Scanner/refs/heads/main/ssl_issues.json"
        fetch_latest_issues(remote_ssl_issues_url)

        return None

    def createMenuItems(self, invocation):
        context_menu = ArrayList()

        if self._nmap_installed:
            context_menu_item_nmap = JMenuItem("Use NMAP")
            context_menu_item_nmap.addActionListener(self._menuSSLScanner(invocation, self._callbacks, self._helpers, "nmap"))
            context_menu.add(context_menu_item_nmap)

        if self._sslscan_installed:
            context_menu_item_sslscan = JMenuItem("Use SSLScan")
            context_menu_item_sslscan.addActionListener(self._menuSSLScanner(invocation, self._callbacks, self._helpers, "sslscan"))
            context_menu.add(context_menu_item_sslscan)

        return context_menu

    class _menuSSLScanner(ActionListener):
        def __init__(self, invocation, callbacks, helpers, scanner):
            self._invocation = invocation
            self._callbacks = callbacks
            self._helpers = helpers
            self._scanner = scanner

        def actionPerformed(self, event):
            selected_messages = self._invocation.getSelectedMessages()
            if selected_messages:
                for messageInfo in selected_messages:
                    httpService = messageInfo.getHttpService()
                    host = messageInfo.getHttpService().getHost()
                    port = messageInfo.getHttpService().getPort()
                    protocol = messageInfo.getHttpService().getProtocol()
                    request_url = self._helpers.analyzeRequest(messageInfo).getUrl()

                    # Skip if not https and verify if URL is Out-of-Scope
                    if str(protocol).lower() == "https":
                        if not self._callbacks.isInScope(request_url):
                            continue_scan = JOptionPane.showConfirmDialog(
                                None,
                                "The selected URL {} is not In-Scope. Continue SSL/TLS Scan?".format(request_url),
                                "SecSci SSL/TLS Scanner",
                                JOptionPane.YES_NO_OPTION,
                                JOptionPane.WARNING_MESSAGE)

                            if continue_scan == JOptionPane.YES_OPTION:
                                print("[INFO] {} is not In-Scope: SSL/TLS scan initiated.".format(request_url))
                            else:
                                print("[INFO] {} is not In-Scope: SSL/TLS scan is cancelled.".format(request_url))
                        else:
                            continue_scan = JOptionPane.YES_OPTION

                        if continue_scan == JOptionPane.YES_OPTION:
                            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                            target = host + ":" + str(port)

                            if target not in hosts:
                                hosts.append(target)
                                if self._scanner == "nmap":
                                    thread = threading.Thread(target=run_sslscan,
                                                     args=(host, port, httpService, request_url, messageInfo,
                                                           self._callbacks, "nmap"))
                                else:
                                    thread = threading.Thread(target=run_sslscan,
                                                              args=(host, port, httpService, request_url, messageInfo,
                                                                    self._callbacks, "sslscan"))
                                thread.name = "SecSci-TLS-Scanner-{}-{}".format(host, timestamp)
                                thread.start()
                            else:
                                print("[INFO] {} is already scanned.".format(target))
                    else:
                        print("[INFO] {} is not running on HTTPS protocol.".format(request_url))

    def processHttpMessage(self, toolFlag, messageIsRequest, messageInfo):
        # Only act on responses (not requests)
        if messageIsRequest:
            return None

        httpService = messageInfo.getHttpService()
        host = httpService.getHost()
        port = httpService.getPort()
        protocol = httpService.getProtocol()
        request_url = self._helpers.analyzeRequest(messageInfo).getUrl()

        # Skip if not https or the URL is out-of-scope
        if str(protocol).lower() != "https" or not self._callbacks.isInScope(request_url):
            return None

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        target = host + ":" + str(port)

        if target not in hosts:
            hosts.append(target)
            # threading.Thread(target=run_nmap_ssl_scan, args=(host, port)).start()
            # acr
            thread = threading.Thread(target=run_sslscan,
                                      args=(host, port, httpService, request_url, messageInfo, self._callbacks, self._ssl_scanner))
            thread.name = "SecSci-TLS-Scanner-{}-{}".format(host, timestamp)
            thread.start()

        return None

            # print("[INFO] No weak cipher support on %s:%s" % (host, port))


class SSLScanIssue(IScanIssue):
    def __init__(self, httpService, url, httpMessages, name, detail, severity):
        self._httpService = httpService
        self._url = url
        self._httpMessages = httpMessages
        self._name = name
        self._detail = detail
        self._severity = severity

    def getUrl(self): return self._url
    def getIssueName(self): return self._name
    def getIssueType(self): return 0
    def getSeverity(self): return self._severity
    def getConfidence(self): return "Certain"
    def getIssueBackground(self): return None
    def getRemediationBackground(self): return None
    def getIssueDetail(self): return self._detail
    def getRemediationDetail(self): return None
    def getHttpMessages(self): return self._httpMessages
    def getHttpService(self): return self._httpService
