"""Installscript im README: Syntax, eingebetteter Wrapper, Vorlage der Ausnahmeliste, Abgleich mit den Releases."""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from _laden import ROOT, SKRIPT, scanner

README = os.path.join(ROOT, "README.md")
KOPF = "#!/bin/bash\n# container-security-scan installieren"


def installscript(readme):
    """Den Codeblock mit dem Installscript aus dem Text des README holen (genau einer)."""
    bloecke = re.findall(r"^```bash\n(%s.*?)^```$" % re.escape(KOPF), readme, re.S | re.M)
    if len(bloecke) != 1:
        raise AssertionError("README: %d Installscripts statt genau einem" % len(bloecke))
    return bloecke[0]


def heredoc(script, marke):
    m = re.search(r"<<'%s'\n(.*?\n)%s\n" % (marke, marke), script, re.S)
    if not m:
        raise AssertionError("Installscript: Here-Dokument %s fehlt" % marke)
    return m.group(1)


def wert(script, name):
    m = re.search(r"^%s=(\S+)" % name, script, re.M)
    if not m:
        raise AssertionError("Installscript: %s fehlt" % name)
    return m.group(1)


def lesen(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class InstallscriptTest(unittest.TestCase):
    def setUp(self):
        self.readme = lesen(README)
        self.script = installscript(self.readme)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def bash_n(self, text):
        path = os.path.join(self.tmp, "x.sh")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        r = subprocess.run(["bash", "-n", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_syntax(self):
        self.bash_n(self.script)
        wrapper = heredoc(self.script, "LAUF")
        self.assertTrue(wrapper.startswith("#!/bin/bash\n"))
        for platzhalter in ("@VERSION@", "@SHA256@", "@QUELLE@"):   # das Installscript ersetzt genau diese
            self.assertIn(platzhalter, wrapper)
            self.assertIn("s/%s/" % platzhalter, self.script)
        self.assertEqual(set(re.findall(r"@\w+@", wrapper)), {"@VERSION@", "@SHA256@", "@QUELLE@"})
        self.bash_n(wrapper)

    def test_version_und_pruefsumme(self):
        version = wert(self.script, "VERSION")
        self.assertRegex(version, r"^v\d+\.\d+\.\d+$")
        self.assertRegex(wert(self.script, "SHA256"), r"^[0-9a-f]{64}$")
        # Link auf das README des Releases, aus dem Admins das Installscript kopieren
        self.assertIn("aktuell [%s](https://github.com/felixlohmeier/container-security-scan/blob/%s/README.md"
                      % (version, version), self.readme)

    def test_wrapper_isoliert_und_geprueft(self):
        wrapper = heredoc(self.script, "LAUF")
        self.assertIn('sha256sum -c --status', wrapper)
        aufrufe = re.findall(r'(\S+) "\$CODE"', wrapper)
        self.assertTrue(aufrufe)
        self.assertEqual(set(aufrufe), {"-I"}, "Code nur über python3 -I starten")
        self.assertNotRegex(wrapper, r"(?m)^\s*\"\$CODE\"", "Code nicht direkt über die Shebang-Zeile starten")

    def liste(self, text):
        path = os.path.join(self.tmp, "ausnahmen.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(path, 0o644)
        return scanner.ausnahmen_laden(path)

    def test_ausnahmen_vorlage(self):
        vorlage = heredoc(self.script, "AUSNAHMEN")
        self.assertEqual(self.liste(vorlage), [], "die Vorlage darf nichts ausblenden")
        beispiele = re.findall(r"^# ((?:CVE|CONF)-\S+ .*)$", vorlage, re.M)
        self.assertGreaterEqual(len(beispiele), 2)
        aktiviert = re.sub(r"^# ((?:CVE|CONF)-\S+ )", r"\1", vorlage, flags=re.M)
        eintraege = self.liste(aktiviert)
        self.assertEqual(len(eintraege), len(beispiele), "jedes Beispiel muss gültig sein")
        self.assertTrue(any(e["id"].startswith("CONF-") for e in eintraege))
        # die CONF-Kennung gibt es im Skript wirklich
        for e in eintraege:
            if e["id"].startswith("CONF-"):
                self.assertIn('"%s"' % e["id"], lesen(SKRIPT))


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout


@unittest.skipUnless(os.environ.get("CSS_RELEASE_TESTS"), "nur mit CSS_RELEASE_TESTS=1 und voller Git-Historie")
class ReleaseTest(unittest.TestCase):
    """README und Releases passen zusammen (in der GitHub Action mit fetch-depth: 0)."""

    def setUp(self):
        self.script = installscript(lesen(README))
        self.version = wert(self.script, "VERSION")
        self.sha256 = wert(self.script, "SHA256")

    def tag_vorhanden(self):
        return bool(git("tag", "--list", self.version).strip())

    def test_pruefsumme_und_installscript(self):
        if self.tag_vorhanden():
            code = git("show", "%s:container-security-scan.py" % self.version)
            self.assertEqual(hashlib.sha256(code).hexdigest(), self.sha256,
                             "SHA256 im Installscript passt nicht zum Skript im Tag %s" % self.version)
            alt = installscript(git("show", "%s:README.md" % self.version).decode("utf-8"))
            self.assertEqual(self.script, alt, "Installscript geändert: neue VERSION eintragen (README: Releases)")
        else:   # Release in Vorbereitung
            with open(SKRIPT, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), self.sha256,
                                 "Tag %s fehlt noch: SHA256 muss zum aktuellen Skript passen" % self.version)

    def test_tag_entspricht_version(self):
        if os.environ.get("GITHUB_REF_TYPE") != "tag":
            self.skipTest("kein Push eines Tags")
        self.assertEqual(os.environ.get("GITHUB_REF_NAME"), self.version,
                         "Tag und VERSION im Installscript stimmen nicht überein")


if __name__ == "__main__":
    unittest.main()
