# container-security-scan

Schwachstellen-Scan für **laufende Docker-Container** – mit Fokus auf das, was tatsächlich läuft und
von außen erreichbar ist. Ein einzelnes Python-Skript, nur Standardbibliothek, ab Python 3.6 (SLES 15),
rein lesend. Die Schwachstellendaten (gekürzter Auszug aus [OSV](https://osv.dev), dazu Supportende und
aktiv ausgenutzte Lücken) liegen im Branch [`daten`](https://github.com/felixlohmeier/container-security-scan/tree/daten) und werden täglich per GitHub
Action aktualisiert; Paketlisten verlassen den Server nie.

Nach der [Einrichtung](#installation-und-betrieb) (einmalig, wenige Minuten):

```bash
sudo /usr/local/sbin/container-security-scan-lauf
# 0 = ok, 1 = relevante Schwachstellen oder gefährliche Einstellungen, 2 = Fehler/unvollständig
# Berichte unter /var/log/container-security-scan/
```

## Warum?

Übliche Scanner (Trivy, Grype, OSV-Scanner) prüfen **Images** oder Lockfiles. Für den Betrieb zählt,
was im **laufenden** Container steckt und ob es von außen erreichbar ist:

- Inhalte von **Volumes** (z. B. eine PHP-Anwendung samt `vendor/` im Volume) sieht ein Image-Scan nicht.
- **Laufzeiten aus offiziellen Images** (PHP, Node.js, Python sind dort aus dem Quellcode gebaut) haben
  kein OS-Paket – ein reiner Paket-Scan übersieht Lücken in der Laufzeit selbst (Beispiele aus 2026:
  PHP2Shell in PHP, Node2Shell in Node.js).
- **Eingebettete JavaScript-Bibliotheken** (z. B. jQuery 1.x unter `Resources/Public/…`) erkennt Trivy nicht.
- Von Tausenden Funden zählen die, die ein **öffentlich erreichbarer Dienst** tatsächlich lädt – auch
  hinter einem Reverse Proxy (nginx → php-fpm oder Node im Nachbarcontainer).

## Installation und Betrieb

Das Skript läuft als root (oder mit docker-Rechten, was gleichwertig ist: Wer docker steuern darf, ist
faktisch root). Deshalb sind **Code und Daten getrennt** – bitte genau so einrichten:

- **Code** ist genau eine Datei aus einem **Release** (Git-Tag `vX.Y.Z`), root-eigen unter
  `/opt/container-security-scan/`. Das Installscript übernimmt sie nur, wenn ihre SHA-256-Prüfsumme zum Wert
  im Installscript passt, und ersetzt das Verzeichnis vollständig – dort liegt nichts anderes, das als root
  laufen könnte. Aktualisiert wird nie automatisch, nur von Hand nach Prüfung ([Schritt 5](#5-code-aktualisieren)).
- **Daten** (Branch `daten`: nur JSON, kein Code) holt der Benutzer `csscan` ohne Rechte per `git pull`.
- Der Wrapper `container-security-scan-lauf` verbindet beides: Daten als `csscan` aktualisieren, dann als
  root scannen. Er dient für den Aufruf von Hand, per cron und per Rundeck, prüft vor jedem Lauf die
  Prüfsumme des Codes und startet Python isoliert (`python3 -I`: keine Module aus dem Skriptverzeichnis,
  keine `PYTHON*`-Umgebungsvariablen).

```
/opt/container-security-scan/                  Code (nur container-security-scan.py): root, Release mit Prüfsumme
/var/lib/container-security-scan/daten/        Daten (Branch daten): csscan, git pull bei jedem Lauf
/usr/local/sbin/container-security-scan-lauf   Wrapper: root, vom Installscript erzeugt
/etc/container-security-scan/ausnahmen.txt     Ausnahmeliste: root, anfangs nur auskommentierte Beispiele
/var/log/container-security-scan/              Berichte und Logs
```

### 1. Einrichten

Voraussetzungen: Linux mit Docker, Python ≥ 3.6 (SLES 15: `python3`), `git`, `curl`; optional `rpm` (nur für
RPM-Container ohne eigenes `rpm`).

Das Installscript richtet alles ein und dient auch zum Aktualisieren. Es liegt bewusst nicht als Datei im
Repository, damit es niemand ungelesen per `curl … | sudo bash` startet: aus dem README **des Releases**
kopieren (aktuell [v1.0.0](https://github.com/felixlohmeier/container-security-scan/blob/v1.0.0/README.md#1-einrichten)),
als Datei speichern (z. B. `container-security-scan-installieren.sh`), lesen, bei Bedarf `PROXY` setzen, dann:

```bash
sudo bash container-security-scan-installieren.sh
```

- Lädt `container-security-scan.py` aus dem Tag `VERSION` und bricht ab, wenn die Prüfsumme nicht passt –
  dann ist nichts verändert. Ein verschobener Tag oder ein manipulierter Download fällt so auf; die
  Prüfsumme lässt sich unabhängig nachrechnen ([Schritt 5](#5-code-aktualisieren)).
- Legt den Benutzer `csscan` und den Clone der Daten an, falls sie fehlen.
- Ersetzt `/opt/container-security-scan/` vollständig (auch einen Git-Checkout aus einer früheren
  Einrichtung) und den Wrapper.
- Legt die Ausnahmeliste mit auskommentierten Beispielen an, falls sie fehlt. Eine vorhandene bleibt
  unverändert, ebenso Daten, Berichte, cron und sudoers.
- Läuft gerade ein Scan, bricht es ab, statt den Code darunter auszutauschen.

```bash
#!/bin/bash
# container-security-scan installieren oder aktualisieren (README: Installation und Betrieb).
# Aufruf als root: sudo bash container-security-scan-installieren.sh
# Ersetzt Code und Wrapper vollständig durch den Stand von VERSION, nur bei passender Prüfsumme.
# Legt bei Bedarf an: Benutzer csscan, Daten, Ausnahmeliste (nur auskommentierte Beispiele).
# Unverändert bleiben: Daten, eine vorhandene Ausnahmeliste, Berichte, cron und sudoers.
set -euo pipefail
VERSION=v1.0.0
SHA256=e6d44db95bab6ce4ab0c881ebbba3cec2fa3aff9fce78c6161acddae81b13ee9
PROXY=""            # nur mit Proxy, z. B. http://proxy:3128 (Download und git pull als csscan)
DATEI=""            # nur ohne Zugang zu GitHub: Pfad zu container-security-scan.py aus dem Tag VERSION
QUELLE=github       # Daten: github (Branch daten) oder osv (direkt von OSV, README: Sonderfall)

REPO=felixlohmeier/container-security-scan
CODE=/opt/container-security-scan
D=/var/lib/container-security-scan
LAUF=/usr/local/sbin/container-security-scan-lauf
ETC=/etc/container-security-scan
PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022
[[ -z $DATEI || $DATEI = /* ]] || DATEI=$PWD/$DATEI
cd /
fehler() { echo "FEHLER: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fehler "als root ausführen: sudo bash $0"
[[ $VERSION =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ && $SHA256 =~ ^[0-9a-f]{64}$ ]] || fehler "VERSION/SHA256 ungültig"
[[ $QUELLE =~ ^(github|osv)$ ]] || fehler "QUELLE muss github oder osv sein"
for p in curl git python3 runuser flock sha256sum useradd; do
  command -v "$p" >/dev/null || fehler "$p fehlt"
done
umask 077; exec 9>/run/container-security-scan.lock; umask 022
chmod 600 /run/container-security-scan.lock   # sonst könnte jeder sie halten und Scans blockieren
flock -n 9 || fehler "ein Scan läuft gerade; danach erneut ausführen"
TMP=$(mktemp -d)
NEU=""
trap 'rm -rf "$TMP" "$LAUF.neu" ${NEU:+"$NEU"}' EXIT

# 1. Code holen und prüfen (noch nichts installiert)
if [ -n "$DATEI" ]; then
  cp -- "$DATEI" "$TMP/scan.py"
else
  CURL=(curl --proto =https --tlsv1.2 -fsSL)
  [ -z "$PROXY" ] || CURL+=(--proxy "$PROXY")
  "${CURL[@]}" -o "$TMP/scan.py" \
      "https://raw.githubusercontent.com/$REPO/refs/tags/$VERSION/container-security-scan.py" \
      || fehler "Download von $VERSION fehlgeschlagen"
fi
echo "$SHA256  $TMP/scan.py" | sha256sum -c --status \
    || fehler "Prüfsumme passt nicht zu $VERSION – nichts installiert"
python3 -I "$TMP/scan.py" --help >/dev/null || fehler "Skript läuft nicht mit $(python3 -V 2>&1)"

# 2. Benutzer csscan und Daten, falls sie fehlen
id -u csscan >/dev/null 2>&1 || useradd -r -U -m -d "$D" -s /sbin/nologin csscan
[ -z "$PROXY" ] || runuser -u csscan -- git config --global http.proxy "$PROXY"
if [ "$QUELLE" = github ] && [ ! -e "$D/daten" ]; then
  runuser -u csscan -- git clone --quiet --single-branch --branch daten "https://github.com/$REPO.git" "$D/daten" \
      || fehler "Daten nicht geholt (git clone als csscan)"
fi

# 3. Wrapper erzeugen und prüfen (noch nichts ersetzt)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SHA256@/$SHA256/" -e "s/@QUELLE@/$QUELLE/" > "$TMP/lauf" <<'LAUF'
#!/bin/bash
# Vom Installscript erzeugt – nicht von Hand ändern, sondern das Installscript erneut ausführen.
# Daten als csscan aktualisieren, dann als root mit dem installierten Code scannen.
# Aufruf von Hand, per cron (--mail) oder per Rundeck (sudo, ohne Argumente).
# Von Hand optional genau ein Container (Name oder ID) statt aller: ... [--mail] [container]
# Ausgabe auf die Konsole und ins Log; letzte Zeile "ERGEBNIS: …"; Rückgabewert 0/1/2 wie das Skript.
set -u
PATH=/usr/sbin:/usr/bin:/sbin:/bin
VERSION=@VERSION@
SHA256=@SHA256@
QUELLE=@QUELLE@
CODE=/opt/container-security-scan/container-security-scan.py
D=/var/lib/container-security-scan
OUT=/var/log/container-security-scan
AUSNAHMEN=/etc/container-security-scan/ausnahmen.txt   # wird verwendet, wenn vorhanden
MAIL=nein; [ "${1:-}" = --mail ] && { MAIL=ja; shift; }
ZIEL=(--alle-container)                 # Standard: alle laufenden Container
if [ $# -gt 0 ]; then                   # Name/ID wie bei Docker, nie mit "-" am Anfang (sonst Option)
  [[ $# -eq 1 && $1 =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] \
      || { echo "FEHLER: Aufruf: $0 [--mail] [container]"; exit 2; }
  ZIEL=("$1")
fi

cd / && umask 077                       # Berichte enthalten u. a. Prozess-Kommandozeilen
exec 9>/run/container-security-scan.lock
flock -n 9 || { echo "ERGEBNIS: UNVOLLSTAENDIG (Scan läuft bereits) – $(hostname)"; exit 2; }
mkdir -p "$OUT/berichte"
LOG=$OUT/$(date +%F_%H%M%S).txt
[ "$QUELLE" = osv ] && ARGS=(--db "$D/osv-db") || ARGS=(--db "$D/daten")
[ -f "$AUSNAHMEN" ] && ARGS+=(--ausnahmen "$AUSNAHMEN")
{
  echo "container-security-scan $VERSION"
  echo "$SHA256  $CODE" | sha256sum -c --status \
      || { echo "FEHLER: $CODE entspricht nicht $VERSION – Installscript erneut ausführen"; exit 2; }
  if [ "$QUELLE" = osv ]; then
    runuser -u csscan -- python3 -I "$CODE" --db "$D/osv-db" --db-aktualisieren \
        || { echo "FEHLER: Daten nicht aktualisiert (direkt von OSV)"; exit 2; }
  else
    runuser -u csscan -- git -C "$D/daten" pull --ff-only --quiet \
        || { echo "FEHLER: Daten nicht aktualisiert (git pull als csscan)"; exit 2; }
  fi
  python3 -I "$CODE" "${ARGS[@]}" --nur-behebbare "${ZIEL[@]}" "$OUT/berichte"
} 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
case $rc in 0) e=OK ;; 1) e=FUNDE ;; *) e=UNVOLLSTAENDIG; rc=2 ;; esac
echo "ERGEBNIS: $e (Rückgabewert $rc) – $(hostname)" | tee -a "$LOG"
[ "$MAIL" = ja ] && [ $rc -ne 0 ] && mail -s "container-security-scan $(hostname): $e" root < "$LOG"
exit $rc
LAUF
bash -n "$TMP/lauf"

# 4. Code und Wrapper ersetzen; das Code-Verzeichnis vollständig, danach liegt dort nur das Skript.
#    Bricht es dazwischen ab, verweigert der Wrapper den Scan (Prüfsumme) bis zum nächsten Lauf hiervon.
NEU=$(mktemp -d /opt/.container-security-scan.XXXXXX)
install -o root -g root -m 755 "$TMP/scan.py" "$NEU/container-security-scan.py"
chown root:root "$NEU" && chmod 755 "$NEU"
install -o root -g root -m 755 "$TMP/lauf" "$LAUF.neu"
rm -rf "$CODE"
mv "$NEU" "$CODE"
mv "$LAUF.neu" "$LAUF"

# 5. Ausnahmeliste: nur anlegen, wenn sie fehlt – nie überschreiben
install -d -o root -g root -m 755 "$ETC"
if [ ! -e "$ETC/ausnahmen.txt" ]; then
  cat > "$TMP/ausnahmen.txt" <<'AUSNAHMEN'
# Ausnahmeliste für container-security-scan – Format und Wirkung: README, Abschnitt "Ausnahmen".
# Je Zeile: Kennung wie im Bericht (CVE, Kennung der Quelle oder CONF-…), Paket wie in der Spalte
# "Paket" (bei CONF-… der Containername) oder * für alle, gültig bis JJJJ-MM-TT, Begründung.
# Nach Ablauf zählt der Fund wieder (mit Warnung im Bericht). Eine fehlerhafte Zeile bricht den Scan
# ab (Rückgabewert 2). Nur root darf diese Datei ändern können, sonst bricht der Scan ebenfalls ab.
# Beispiele: zum Verwenden "# " am Zeilenanfang entfernen und an den eigenen Fall anpassen.
#
# Kennung         Paket oder *  gültig bis  Begründung
# CVE-2024-8926   php           2027-06-30  betrifft nur PHP-CGI unter Windows (geprüft 2026-11-05)
# CVE-2026-107814 mariadb       2027-03-31  betrifft nur die RPM-Pakete von MariaDB, hier Ubuntu-Image
# CONF-SOCKET     traefik       2027-03-31  Docker-Provider liest Labels über den Socket; Socket-Proxy geplant
AUSNAHMEN
  install -o root -g root -m 644 "$TMP/ausnahmen.txt" "$ETC/ausnahmen.txt"
  echo "Ausnahmeliste angelegt (nur Beispiele): $ETC/ausnahmen.txt"
fi

echo "container-security-scan $VERSION installiert: $CODE/container-security-scan.py, $LAUF"
echo "Testlauf: sudo $LAUF"
```

Danach `sudo /usr/local/sbin/container-security-scan-lauf` ([Schritt 2](#2-bei-bedarf-von-hand-prüfen)) und den
täglichen Lauf einrichten ([Schritt 3](#3-täglich-cron-oder-rundeck)).

**Ausnahmeliste:** `/etc/container-security-scan/ausnahmen.txt` enthält anfangs nur auskommentierte
Beispiele (darunter eines für eine [gefährliche Einstellung](#gefährliche-einstellungen-des-containers)
`CONF-…`) und blendet nichts aus. Einträge für Fehlalarme und bewusst akzeptierte Risiken, mit Begründung
und Ablaufdatum, kommen später aus den Berichten ([Schritt 4](#4-auf-das-ergebnis-reagieren)). Die Datei muss
root gehören und darf nur für root beschreibbar sein, sonst bricht der Scan ab (Rückgabewert 2). Format und
Wirkung: [Ausnahmen](#ausnahmen).

### 2. Bei Bedarf von Hand prüfen

```bash
sudo /usr/local/sbin/container-security-scan-lauf
```

Geprüft werden alle laufenden Container: zuerst die erreichbaren (siehe [Erreichbarkeit](#erreichbarkeit))
samt den Backends hinter ihren Reverse Proxys, dann alle übrigen. Was nicht als erreichbar erkannt wird,
fehlt so nicht, sondern erscheint mindestens als P2. Einen einzelnen Container (z. B. bei der Entwicklung)
mit denselben Sicherheitsvorkehrungen – Daten aktualisieren, Sperre, Ausnahmeliste, Log, `ERGEBNIS:`-Zeile –,
aber ohne Erreichbarkeit über Proxys in anderen Containern:

```bash
sudo /usr/local/sbin/container-security-scan-lauf <container>
```

Erlaubt ist genau ein Name oder eine ID, wie Docker sie vergibt; alles andere (mehrere Argumente, Optionen,
Tippfehler wie `--mial`) bricht mit Rückgabewert 2 ab, statt still etwas anderes zu scannen.

### 3. Täglich: cron oder Rundeck

Neue Schwachstellen erscheinen in den OSV-Daten typischerweise 1–2 Tage nach Veröffentlichung; die GitHub
Action übernimmt sie täglich um 03:17 UTC in den Branch `daten`, GitHub startet sie oft bis zu einer Stunde
später. Den Scan mit Abstand ansetzen, z. B. 07:23 Ortszeit; welcher Datenstand verwendet wurde, steht im
Bericht unter „Datenbank“.

**cron** – `/etc/cron.d/container-security-scan` (Mail an root nur bei Rückgabewert 1 oder 2):

```cron
MAILTO=""
23 7 * * * root /usr/local/sbin/container-security-scan-lauf --mail >/dev/null 2>&1
```

**Rundeck** – statt cron. Rundeck darf per sudo nur genau den Wrapper starten, ohne Argumente: keine
allgemeinen root-Rechte, kein `docker`, kein `python3`. Wer Rundeck übernimmt, kann so Scans auslösen,
aber nicht root auf den Servern werden.

```bash
cat > /etc/sudoers.d/rundeck-container-scan <<'EOF'
rundeck ALL=(root) NOPASSWD: /usr/local/sbin/container-security-scan-lauf ""
EOF
chmod 440 /etc/sudoers.d/rundeck-container-scan && visudo -c
```

- `""` am Ende verbietet zusätzliche Argumente – so lassen, auch wenn der Wrapper von Hand einen Container
  annimmt (Rundeck scannt immer alle); kein `*`, das ließe beliebige Argumente zu. `rundeck` an den eigenen
  Benutzer anpassen; bei `requiretty` zusätzlich `Defaults:rundeck !requiretty`.
- Job mit dem Schritt „Command“: `sudo -n /usr/local/sbin/container-security-scan-lauf` – kein Schritt
  „Script“, der eine Datei auf den Server kopiert (dafür bräuchte Rundeck allgemeine root-Rechte).
- Zeitplan wie oben; Zeitlimit großzügig (ein Container kann bis zu 30 Minuten dauern); Server, die sich
  Ressourcen teilen (VMs auf demselben Host), nacheinander oder in kleinen Gruppen abarbeiten.
- Benachrichtigung bei Fehlschlag. Rückgabewert 1 und 2 sind in Rundeck beide rot; die letzte Zeile
  `ERGEBNIS: FUNDE` bzw. `ERGEBNIS: UNVOLLSTAENDIG` unterscheidet sie. Berichte und Logs bleiben auf dem
  jeweiligen Server, die Konsolenausgabe steht zusätzlich im Rundeck-Log: je Container die Zusammenfassung,
  Warnungen und **jeder relevante Fund** in einer Zeile (neue zuerst, mit `NEU:` markiert). Für alle
  übrigen Befunde, Dienste und Belege den Bericht auf dem Server ansehen (Pfad in der Zusammenfassung).
- Optional den SSH-Schlüssel auf diesen Befehl festlegen (`~rundeck/.ssh/authorized_keys` auf dem Server,
  eigener Schlüssel nur für diesen Job):

  ```
  command="sudo -n /usr/local/sbin/container-security-scan-lauf",from="<IP des Rundeck-Servers>",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding ssh-ed25519 AAAA… rundeck-container-scan
  ```

### 4. Auf das Ergebnis reagieren

- **0** – nichts zu tun.
- **1** – Funde im Bericht prüfen (seit dem letzten Lauf neue sind markiert) und Images aktualisieren bzw.
  [gefährliche Einstellungen](#gefährliche-einstellungen-des-containers) beseitigen. Fehlalarme und bewusst
  akzeptierte Risiken mit Begründung und Ablaufdatum in die [Ausnahmeliste](#ausnahmen), nicht die
  Alarmierung abschalten.
- **2** – Ursache beheben (Daten nicht aktualisiert oder veraltet, Container nicht lesbar …), sonst ist
  die Überwachung blind. Details: [Rückgabewert](#rückgabewert).
- Warnungen (Supportende, öffentlicher Dienst als root …) ändern den Rückgabewert nicht. Der Host selbst
  ist nicht Teil des Scans (SLES: `zypper list-patches --category security`).

### 5. Code aktualisieren

Nur nach Prüfung – jede Änderung am Code läuft danach als root:

1. Änderungen seit der installierten Version ansehen, z. B.
   `https://github.com/felixlohmeier/container-security-scan/compare/v1.0.0...v1.1.0`, dazu die Hinweise im
   Release. Die installierte Version steht in der ersten Zeile jedes Logs und im Wrapper
   (`grep ^VERSION= /usr/local/sbin/container-security-scan-lauf`).
2. Das Installscript aus dem README des neuen Releases kopieren – es enthält Version und Prüfsumme genau
   dieses Stands – und wie in [Schritt 1](#1-einrichten) ausführen. Code und Wrapper werden vollständig
   ersetzt; Daten, Ausnahmeliste und Berichte bleiben. Eigene Werte (`PROXY`, `DATEI`, `QUELLE`) wieder eintragen.

Wer die Prüfsumme unabhängig von GitHubs Weboberfläche nachrechnen will (nicht als root nötig):

```bash
git clone https://github.com/felixlohmeier/container-security-scan.git /tmp/css && cd /tmp/css
git diff v1.0.0 v1.1.0 -- container-security-scan.py         # Änderungen am Code
git show v1.1.0:container-security-scan.py | sha256sum        # = SHA256 im Installscript von v1.1.0
```

Nie: den Code automatisch (per cron) aktualisieren, das Installscript ungelesen per `curl … | sudo bash`
ausführen, den Code aus dem Daten-Clone starten, `--db-aktualisieren` als root (wird abgelehnt) – und keine
Datei, die ein anderer Benutzer ändern kann, als root oder mit docker-Rechten ausführen.

## Ergebnis verstehen

### Rückgabewert

| Wert | Bedeutung |
|---|---|
| `0` | keine relevanten Schwachstellen |
| `1` | relevante Schwachstellen oder [gefährliche Einstellungen](#gefährliche-einstellungen-des-containers) gefunden |
| `2` | Fehler oder **Prüfung unvollständig** – nie als „sauber“ werten. Z. B.: docker nicht erreichbar, Container läuft nicht, Daten fehlen für ein benötigtes Ökosystem oder sind älter als 3 Tage, keine Paketdatenbank im Container, Dateien nicht vollständig lesbar (z. B. unlesbare Verzeichnisse; während der Prüfung gelöschte oder geänderte Dateien zählen nicht), nginx- bzw. Apache-Konfiguration nicht lesbar (im Container oder eines Proxys auf dem Host), Distribution ohne aktuelle Sicherheitsdaten (EOL), Ausnahmeliste fehlerhaft. |

**Relevant** ist P1 CRITICAL/HIGH und P2 CRITICAL (anpassbar über `RELEVANT` am Anfang des Skripts), dazu
**jede aktiv ausgenutzte Lücke** aus dem [KEV-Katalog der CISA](https://www.cisa.gov/known-exploited-vulnerabilities-catalog),
unabhängig von Priorität und Schweregrad. Mit `--nur-behebbare` (so im Wrapper) gilt für alle, auch für
KEV-Funde: nur mit verfügbarem Fix. Grund für KEV: „Genutzt von“ ist eine Momentaufnahme. Programme, die eine
Anwendung nur bei Bedarf startet (ImageMagick, Ghostscript, ffmpeg beim Hochladen), erscheinen als P4; ist
eine solche Lücke aktiv ausgenutzt, soll sie trotzdem melden. Nicht relevant sind Funde aus der
Ausnahmeliste und Funde, die laut Titel nur Windows betreffen (siehe [Bewertung](#bewertung-der-funde)).

### Priorität

| | Bedeutung |
|---|---|
| **P1** | genutzt von einem erreichbaren Dienst (Intranet oder Internet, siehe [Erreichbarkeit](#erreichbarkeit)) |
| **P2** | genutzt von einem Dienst mit internem Port |
| **P3** | genutzt nur von einem Prozess ohne offenen Port |
| **P4** | installiert, aber nicht in Benutzung erkannt; oder Entwicklungsabhängigkeit (dev) |

„Genutzt von“ wird über `/proc` ermittelt: Programm und geladene Bibliotheken, geöffnete Dateien (JARs),
offene TCP/UDP-Ports; für npm/Composer/PyPI über das Projektverzeichnis (Arbeitsverzeichnis, Skriptpfad,
venv, Docroot aus der nginx-/Apache-Konfiguration). Welche Pakete eine Anwendung tatsächlich importiert,
ist von außen nicht sichtbar. Lässt sich ein veröffentlichter Port keinem Prozess zuordnen, werden
vorsichtshalber alle Komponenten des Containers als öffentlich genutzt gewertet (mit Warnung).

### Erreichbarkeit

„Öffentlich“ heißt im Bericht: von außerhalb des Docker-Hosts erreichbar. Ob aus dem Internet oder nur aus
dem Intranet, ist auf dem Server nicht erkennbar (Firewall, NAT, vorgelagerte Load Balancer) und wird gleich
gewertet. Das Ergebnis hängt nur von der Docker-Konfiguration ab, nicht vom Netz: Eine Testumgebung im
internen Netz mit derselben Konfiguration findet dieselben relevanten Funde wie die Produktion.

Grundsatz: **im Zweifel erreichbar.** Als intern gilt ein Dienst nur, wenn der Weg dorthin vollständig
bekannt ist. Ein Dienst, der nur auf Loopback lauscht (127.0.0.1, ::1), ist nie erreichbar. Sonst gilt er als
erreichbar, wenn eine der folgenden Bedingungen zutrifft:

| Weg | Erkennung |
|---|---|
| Port veröffentlicht | `docker inspect`, auch an `127.0.0.1` (dann meist hinter einem Reverse Proxy auf dem Host) |
| Host-Netzwerk | `network_mode: host` |
| eigene Adresse im LAN | Docker-Netz mit Treiber macvlan/ipvlan oder `gateway_mode_ipv4/6` `routed` bzw. `nat-unprotected` |
| gemeinsamer Netzwerk-Namespace | `network_mode: container:…`/`service:…` (z. B. VPN- oder Sidecar-Container): es gelten die Ports des Spenders; ein Ziel des Spenders wird an alle Container dieses Namespace weitergegeben |
| hinter einem erreichbaren nginx/Apache | Backends aus `nginx -T` bzw. der Apache-Konfiguration (`proxy_pass`, `fastcgi_pass`, `upstream`, `ProxyPass`, `SetHandler proxy:`), auch über mehrere Proxys hintereinander. Variablen aus `set` und `map` (`proxy_pass $backend` mit `resolver`) werden aufgelöst; Ziele per Container-Name, Alias, Compose-Dienst, IP oder `<name>.<netz>` |
| hinter einem erreichbaren Traefik bzw. caddy-docker-proxy | Ziele aus Docker-Labels (`traefik.*.services.*.loadbalancer.server.port`, `caddy.reverse_proxy: {{upstreams …}}`) |
| hinter einem Reverse Proxy **direkt auf dem Host** | nginx/Apache außerhalb von Docker (Programm mit dem Wurzelverzeichnis des Hosts, nicht in der cgroup eines Containers), das nicht nur auf Loopback lauscht: Konfiguration wie oben, Ziele über die Container-IP (z. B. `proxy_pass http://172.18.0.5:3000`). Ergebnis auf der Konsole als `Host: …`; gilt auch für den Einzelscan |
| aufgerufen von einer erreichbaren Anwendung | z. B. API-Gateway in Java/Node oder eine App, die einen internen HTTP-Dienst aufruft: **Ziel-URLs** (`http(s)://`, `ws(s)://`, `grpc(s)://` auf einen anderen Container) in der Umgebung des Containers (`docker inspect`) oder der Kommandozeile – `mysql://`, `redis://` u. ä. zählen nicht – sowie zum Zeitpunkt des Scans **offene TCP-Verbindungen** zu einem Port eines anderen Containers. Gilt auch für Worker hinter einem Webserver im selben Container (php-fpm hinter nginx). Ausgenommen sind Datenbanken, Caches und Message Broker als Ziel (MySQL/MariaDB, PostgreSQL, Redis/Valkey, MongoDB, Memcached, RabbitMQ, Elasticsearch/OpenSearch, Solr, Kafka u. a.): die Anwendung ruft sie auf, leitet aber keine Anfragen von außen durch. Lauscht auf dem Ziel-Port nichts (z. B. URL für eine andere Umgebung), bleibt es ohne Folgen. Im Bericht der Anwendung als `Aufruf: Container …, Port … (Quelle)`; Werte der Umgebung erscheinen nicht (Zugangsdaten) |
| hinter einem Tunnel-Agenten | cloudflared, frpc, ngrok, chisel – im Container oder auf dem Host: leiten Verkehr von außen weiter, ohne zu lauschen; gelten immer als erreichbar und nicht auswertbar (siehe nächste Zeile). Container mit einem solchen Image bzw. Befehl werden vorgezogen |
| **möglicherweise** erreichbar | Container im selben Docker-Netz wie ein erreichbarer Dienst, dessen Weiterleitungen nicht vollständig bekannt sind: Traefik, Caddy, HAProxy, Envoy, Varnish u. a. (Konfiguration wird nicht ausgewertet; Labels geben nur einen Teil der Ziele an), nginx-Ziel mit nicht auflösbarer Variable (`proxy_pass http://$host`), nicht lesbare nginx-Konfiguration, veröffentlichter Port ohne erkennbaren Prozess. Bei einem solchen Dienst auf dem Host oder im Host-Netzwerk: alle Container mit einem Docker-Netz (der Host erreicht sie über ihre IP). Mit Warnung je Dienst |

Die Prozesse auf dem Host liest das Skript nur als root vollständig; sonst warnt es (`Host: WARNUNG: Prozesse
auf dem Host nicht vollständig lesbar`), da ein Proxy auf dem Host unerkannt bleiben könnte. Ist die
Konfiguration eines Proxys auf dem Host nicht lesbar, ist die Prüfung unvollständig (Rückgabewert 2).

### Bewertung der Funde

- **Schweregrad:** Einstufung der Distribution (Debian, Ubuntu), sonst Angabe der Quelle, sonst CVSS. Hat
  der zutreffende Eintrag keinen (z. B. Go-Daten, Debian „not yet assigned“), wird die Bewertung derselben
  CVE aus den Bitnami- bzw. Alpine-Daten (CVSS der NVD) übernommen, bei mehreren die höchste. Solche Werte
  sind im Bericht mit `*` markiert.
- **KEV:** aktiv ausgenutzte Lücken sind im Bericht mit `KEV` markiert und immer relevant (siehe oben).
- **Nur Windows:** Daten außerhalb der Distributionen (GitHub, Bitnami) führen auch Lücken, die nur unter
  Windows auftreten (z. B. „On Windows a directory returned by tempfile.mkdtemp() …“). Nennt der Titel das
  eindeutig, steht der Fund mit „nicht gezählt: betrifft laut Titel nur Windows“ in der Tabelle, zählt aber
  nicht als relevant. Die Erkennung ist bewusst vorsichtig (Titel mit „Linux“, „macOS“, „Windows and …“
  bleiben relevant); was sie nicht erkennt, gehört in die Ausnahmeliste.
- **Kernel-Pakete** (`linux-libc-dev`, `linux-headers`, `linux-image-*`, `kernel-*`) werden nicht geprüft:
  Container nutzen den Kernel des Hosts, und Debian/Ubuntu führen alle Kernel-CVEs am Quellpaket `linux` –
  ohne diese Regel sind in einem Debian-Image oft über 90 % der Funde Kernel-CVEs in den Headern.
- **Versionsbereiche der Distribution:** OSV ergänzt Alpine-Daten teils um eine erste betroffene Version
  aus einem anderen Versionszweig („betroffen ab 3.4.0, behoben in 3.3.7-r1“). Liegt der Fix der
  Distribution vor dieser Version, hat sie ihn zurückportiert, ihr Zweig war also betroffen: Solche
  Bereiche gelten ab Version 0. Gültige Angaben bleiben wirksam (curl 8.12.1 ist von einer Lücke ab 8.13.0
  nicht betroffen).

### Gefährliche Einstellungen des Containers

Einstellungen, mit denen aus einer Lücke im Container root auf dem Host wird. Sie sind **immer relevant**
(Rückgabewert 1), unabhängig von Schwachstellen und von `--nur-behebbare`, denn beheben lassen sie sich
immer. Geprüft wird nur, was ein Dienst praktisch nie braucht, aus `docker inspect`:

| Kennung | Befund |
|---|---|
| `CONF-PRIVILEGED` | `--privileged` |
| `CONF-SOCKET` | Socket der Container-Laufzeit eingebunden (`docker.sock`, `containerd.sock`, `podman.sock`) oder ein Verzeichnis, das ihn enthält (`/run`, `/var/run`, `/run/docker`, `/run/containerd`, `/run/podman`, die Host-Wurzel `/`) – auch schreibgeschützt, denn `:ro` verhindert den Zugriff auf einen Socket nicht |
| `CONF-PID-HOST` | `pid=host` |
| `CONF-CAP-…` | zusätzliche Capability, die den Ausbruch erlaubt: `ALL`, `SYS_ADMIN`, `SYS_MODULE`, `SYS_RAWIO`, `DAC_READ_SEARCH`, `BPF` (z. B. `CONF-CAP-SYS-ADMIN`) |
| `CONF-SECCOMP-UNCONFINED`, `CONF-APPARMOR-UNCONFINED` | Schutzprofil ausdrücklich abgeschaltet |
| `CONF-HOST-PFAD` | Host-Pfad beschreibbar eingebunden: `/etc` (ganz oder `passwd`, `shadow`, `sudoers`, `cron*`, `systemd`, `ssh`, `docker`), `/root`, `/boot`, `/bin`, `/sbin`, `/lib*`, `/usr` und `/usr/local` (ganz oder Programme, Bibliotheken), `/proc`, `/sys`, `/dev`, `/home` (ganz oder `~/.ssh`), `/var/lib/docker` (auch das Verzeichnis aller Volumes; einzelne Volumes nicht) |

Mit `--privileged` entfallen die Befunde zu Capabilities und Schutzprofilen (darin enthalten). Typischer
begründeter Fall ist ein Reverse Proxy wie Traefik mit `docker.sock`: besser einen Socket-Proxy mit
Lesezugriff vorschalten (z. B. `tecnativa/docker-socket-proxy`), sonst Ausnahme mit Begründung und
Ablaufdatum (Paket = Containername):

```
CONF-SOCKET       traefik       2027-03-31  liest nur Labels, Umstieg auf Socket-Proxy geplant
```

**Öffentlicher Dienst als root:** Laufen alle Prozesse an einem öffentlichen Port (im Sinne der
[Erreichbarkeit](#erreichbarkeit), auch „möglicherweise“) als root (je Port geprüft), erscheint eine **Warnung** (kein Rückgabewert), z. B. Node oder Python als root. nginx, Apache
und php-fpm (Master root, Worker unprivilegiert am selben Port) zählen nicht. Mit userns-remap oder rootless Docker ist root im
Container nicht root auf dem Host; dann entfällt die Warnung (außer bei `--userns=host`).

Nicht geprüft werden allgemeine Härtung (no-new-privileges, `cap_drop: ALL`, read-only, Limits, Ports nur
an bestimmte IPs) und der Docker-Daemon. Geprüft werden die gescannten (laufenden) Container, mit
`--alle-container` (so im Wrapper) also alle, mit `--oeffentliche` nur die erreichbaren und deren Ziele.

### Ausnahmen

Für Fehlalarme und bewusst akzeptierte Risiken, die die automatische Bewertung nicht erkennt, z. B.
CVE-2024-8926: Der Titel nennt nur „PHP CGI Parameter Injection“, die Lücke betrifft aber nur PHP-CGI unter
Windows. Die Liste liegt auf dem Server, nicht im Repository (einrichten: [Schritt 1](#1-einrichten)):

```
# /etc/container-security-scan/ausnahmen.txt
# Kennung         Paket oder *  gültig bis  Begründung
CVE-2024-8926     php           2027-06-30  betrifft nur PHP-CGI unter Windows (geprüft 2026-11-05)
CVE-2026-107814   mariadb       2027-03-31  betrifft nur die RPM-Pakete von MariaDB, hier Ubuntu-Image
```

- Kennung wie im Bericht (CVE, Kennung der Quelle oder `CONF-…`), Paket wie in der Spalte „Paket“ (bei
  `CONF-…` der Containername) oder `*` für alle.
- Jede Ausnahme braucht ein Ablaufdatum und eine Begründung: Danach zählt der Fund wieder, mit Warnung im
  Bericht. So bleibt keine Ausnahme unbemerkt für immer.
- Ausgenommene Funde stehen im Bericht unter „Nicht gezählt“ und in der Tabelle mit Begründung.
- Eine fehlerhafte Zeile bricht den Scan ab (Rückgabewert 2) statt still etwas auszublenden.

## Aufruf und Optionen

Für den Betrieb genügt der Wrapper ([Installation und Betrieb](#installation-und-betrieb)), auch für einen
einzelnen Container (`container-security-scan-lauf <container>`). Direkter Aufruf für Spezialfälle, immer mit
dem installierten Code, `python3 -I` und `--db`; er verwendet den vorhandenen Datenstand, ohne ihn zu
aktualisieren:

```bash
C=/opt/container-security-scan/container-security-scan.py
DB=/var/lib/container-security-scan/daten
sudo python3 -I $C --db $DB --alle-container <ausgabeverzeichnis>    # wie der Wrapper, ohne Datenaktualisierung
sudo python3 -I $C --db $DB <container> <ausgabeverzeichnis>         # einzelner Container, ohne Datenaktualisierung
sudo python3 -I $C --db $DB --alle <container> <ausgabeverzeichnis>  # alle Befunde in die Tabelle
```

| Option | Bedeutung |
|---|---|
| `--alle-container` | alle laufenden Container: zuerst die erreichbaren und die Backends hinter ihren Proxys (zählen als öffentlich, siehe [Erreichbarkeit](#erreichbarkeit)), dann alle übrigen – **empfohlen**, so im Wrapper. Ein Container, der zwischen Auflistung und Scan entfernt wurde (z. B. `docker run --rm`), wird übersprungen |
| `--oeffentliche` | wie `--alle-container`, aber ohne die übrigen Container |
| `--nur-behebbare` | für den Rückgabewert nur Funde zählen, für die es einen Fix gibt – **empfohlen** für die Alarmierung, sonst melden Container mit offenen, noch unbehobenen CVEs dauerhaft `1` |
| `--alle` | alle Befunde in die Tabelle (sonst P3/P4 nur CRITICAL/HIGH/KEV) |
| `--ausnahmen DATEI` | Ausnahmeliste: passende Funde zählen nicht als relevant, jede Ausnahme mit Begründung und Ablaufdatum (siehe [Ausnahmen](#ausnahmen)) |
| `--db-aktualisieren` | als root abgelehnt (Rückgabewert 2): nie Daten aus dem Netz als root schreiben. Im Git-Checkout den Branch `daten` nach `daten/` holen bzw. dort `git pull` – **nie den Code**; mit `--oekosysteme A,B` zusätzlich diese Ökosysteme direkt von OSV nach `osv-db/` (inkrementell, `--voll` lädt alles neu). Ohne Git-Checkout oder mit `--db`: alle Ökosysteme, die EOL- und die KEV-Daten direkt |
| `--db DIR` | nur diese Datenverzeichnisse verwenden; mehrfach möglich, je Ökosystem gilt das erste, das es enthält. Mit `--db-aktualisieren` genau eines (Ziel). Standard: `daten/` (Clone des Branches `daten`) und `osv-db/` neben dem Skript |
| `--user` | Benutzer für `docker exec` (Standard `0`). Ein anderer Benutzer kann meist nicht alle Verzeichnisse lesen: Die Prüfung gilt dann als unvollständig (`2`), die Meldung nennt die ersten unlesbaren Pfade |

## Ausgabe

Auf der Konsole (beim Wrapper auch im Log, in der Mail und im Rundeck-Log) zuerst Reverse Proxys direkt auf
dem Host mit ihren Zielen (`Host: nginx:443 auf dem Host – erreichbar; Ziele in Containern: app (3000)`), dann
je Container Warnungen, eine Zusammenfassung mit dem Pfad des Berichts und darunter alle relevanten Funde,
neue zuerst:

```
app-php830: RELEVANTE SCHWACHSTELLEN – 6963 Befunde, davon 92 relevant (3 neu); öffentlich: apache2:80 – Bericht: …
app-php830:   NEU: CVE-2026-28780 (CRITICAL) in apache2-bin 2.4.66-1~deb12u1 – behoben in 2.4.67-1~deb12u2 – genutzt von apache2:80
app-php830:   CVE-2025-14179 (CRITICAL) in php 8.3.30 – behoben in 8.3.31 – genutzt von apache2:80
…
```

Je Container im Ausgabeverzeichnis:

- `scan_<name>_<zeit>.md` – Bericht: Ergebnis (relevante Funde, neue zuerst, Warnungen), laufende Dienste
  mit Ports, Proxy-Backends und vHosts, Übersicht nach Priorität, Befundtabelle, nicht automatisch prüfbare
  Komponenten, Anhang (Prozesse, veraltete Bibliotheken im Speicher, Webserver-Konfiguration)
- `scan_<name>_<zeit>.cdx.json` – SBOM im Format CycloneDX 1.5 als Beleg (auch mit Trivy, Grype oder
  Dependency-Track nutzbar)
- `scan_<name>_<zeit>.sha256` – Prüfsummen
- `bekannt_<name>.json` – relevante Funde des letzten Laufs (für die Markierung „neu“)

Beispiele: [`beispiele/`](beispiele/) – ein Lauf `--oeffentliche --nur-behebbare` über eine Testumgebung
([Konsolenausgabe](beispiele/ausgabe_oeffentliche.txt)): nginx als öffentlicher Reverse Proxy vor Node,
Python und PHP-FPM in Nachbarcontainern, PHP 8.3.30 mit Apache (PHP2Shell), Node 22.22.0 nur über den Proxy
erreichbar (Node2Shell), ein PHP-Container mit eingebettetem jQuery 1.10.2 und Java-Bibliotheken, Solr
(Ubuntu-basiert, mit aktiv ausgenutzter Lücke in libbrotli1; Bericht vom 5.11. mit den Ubuntu-Daten).

## Was erfasst wird

| Bereich | Quelle im Container | Abgleich |
|---|---|---|
| OS-Pakete | dpkg (`status`, `status.d`), apk, rpm – inkl. Quellpaket | Debian, Ubuntu, Alpine (optional SUSE, openSUSE) |
| npm | jede `package.json` mit Name und Version | npm |
| Composer | `vendor/composer/installed.json` | Packagist |
| PyPI | `*.dist-info/METADATA`, `*.egg-info` (alle site-packages, auch venvs) | PyPI |
| Java | JAR/WAR/EAR inkl. verschachtelter Archive: `pom.properties`, Tomcat-Version, sonst Manifest/Dateiname (als unsicher markiert) | Maven |
| Go | Build-Info in Go-Programmen (Go-Version und Module) | Go |
| JavaScript | eingebettete Bibliotheken (jQuery, jQuery UI, Chart.js, Bootstrap, Moment, Vue, …) über Kopfkommentar/Dateiname | npm |
| Laufzeiten/Server | Version am Programm: node, php, php-fpm, python, java, nginx, apache, mariadb, postgresql | aus Distributionspaket: über die Distribution; sonst (offizielle Images, Herstellerquellen wie nginx.org, NodeSource, Sury, mariadb.org) über OSV Bitnami |
| Dienste | offene Ports, veröffentlichte Ports, nginx-/Apache-Konfiguration (vHosts, Docroot, Backends → Container) | Priorisierung |

Dateien, die zu einem OS-Paket gehören (z. B. `gosu` aus dem Ubuntu-Paket), werden wie bei Trivy nur
über das OS-Paket geprüft.

## Daten

Der Branch [`daten`](https://github.com/felixlohmeier/container-security-scan/tree/daten) enthält einen gekürzten Auszug aus den OSV-Exporten für Debian, Ubuntu, Alpine, npm, PyPI,
Packagist, Maven, Go und Bitnami (ca. 360 MB, in Git komprimiert ca. 25 MB). Gekürzt heißt: nur die für den
Abgleich nötigen Felder und Einträge; die Ergebnisse sind mit den vollständigen Exporten identisch
(geprüft). Die GitHub Action [`.github/workflows/daten.yml`](.github/workflows/daten.yml) erzeugt die
Daten täglich neu; die Ausgabe ist deterministisch, Commits enthalten nur echte Änderungen. Dazu kommen `eol-daten.json`
([Supportende](#supportende-eol)) und `kev.json` ([aktiv ausgenutzte Lücken](#aktiv-ausgenutzte-lücken-kev)).
Quellen und Lizenzen: [`QUELLEN.md` im Branch `daten`](https://github.com/felixlohmeier/container-security-scan/blob/daten/QUELLEN.md).

Ubuntu ist am stärksten gekürzt: Der Export ist entpackt rund 8 GB groß (als ZIP ca. 800 MB), der
Auszug ca. 190 MB. Weggelassen wird nur, was der Abgleich nie liest: die Listen der Binärpakete (abgeglichen
wird über das Quellpaket), Einträge für Ubuntu Pro, FIPS und Realtime (nicht in Container-Images), Kernel-
Quellpakete (siehe [Bewertung](#bewertung-der-funde)) und die USN-Sammelmeldungen (je CVE gibt es genauere
Einträge). Geprüft (11/2026): Solr und MariaDB (Ubuntu 22.04/24.04) mit identischen Berichten, Abgleich
ca. 5 statt 30 s; dazu je ca. 4000 Paketversionen für Ubuntu 14.04, 16.04 und 18.04 mit über 550 000
identischen Funden.

Ökosysteme, die nicht im Repository liegen (SUSE, openSUSE), lädt `--db-aktualisieren --oekosysteme …`
direkt von OSV nach `osv-db/`. Für Ökosysteme, die es im Branch `daten` schon gibt, ist das wirkungslos:
Je Ökosystem gilt das erste Verzeichnis, das es enthält, und `daten/` (bzw. das erste `--db`) kommt vor
`osv-db/`.

### Sonderfall: Daten direkt von OSV statt über GitHub

Nur nötig, wenn der Server `github.com` nicht erreichen darf oder GitHub auch als Datenquelle
ausgeschlossen sein soll. Dann lädt `csscan` alle Ökosysteme direkt von OSV (`storage.googleapis.com`),
die EOL-Daten von endoflife.date und den KEV-Katalog der CISA. Dafür im Installscript `QUELLE=osv` setzen:
Der Wrapper aktualisiert dann `/var/lib/container-security-scan/osv-db/` als `csscan` mit
`--db-aktualisieren` statt per `git pull`. Darf der Server `github.com` gar nicht erreichen, die Datei
`container-security-scan.py` aus dem Tag auf anderem Weg holen und im Installscript `DATEI=` setzen; die
Prüfsumme gilt genauso.

- **Erster Lauf:** die Gesamtexporte, zusammen ca. 1,2 GB (Stand 11/2026: Ubuntu 800 MB, npm 220 MB,
  Debian 81 MB, PyPI 38 MB, die übrigen je ca. 10 MB; endoflife.date 3 MB, KEV-Katalog 2 MB).
- **Danach inkrementell:** Das Skript liest die Änderungsliste `modified_id.csv` bis zum letzten
  bekannten Stand und lädt nur die geänderten Einträge einzeln. Den Gesamtexport eines Ökosystems lädt
  es neu, wenn seit dem letzten Lauf mehr als 2000 Einträge geändert wurden oder sich mehr als 10 000
  Einzeldateien angesammelt haben. Debian und Ubuntu ändern oft Tausende Einträge an einem Tag; dann
  wird der Gesamtexport neu geladen, bei Ubuntu jeweils ca. 800 MB (Stand 11/2026 ein- bis zweimal pro
  Woche), sonst ca. 30–40 MB pro Tag.
- **Auf der Platte** liegen die ungekürzten Exporte (`<Ökosystem>.zip`, ca. 1,2 GB) und geänderte
  Einträge (`<Ökosystem>.neu/`), nicht der gekürzte Auszug aus dem Repository. Die Ergebnisse sind
  gleich; das Einlesen dauert länger (Debian: ca. 3,5 s statt 1,9 s, Ubuntu: ca. 30 s statt 5 s je
  Container).

| | über GitHub (Standard) | direkt (`--db DIR`) |
|---|---|---|
| Übertragung | erstmals ca. 25–35 MB, täglich nur die Änderungen | erstmals ca. 1,2 GB, täglich ca. 30–40 MB, mit Ubuntu oft ca. 800 MB |
| Speicher | ca. 360 MB plus Git | ca. 1,2 GB |
| Freigabe im Proxy/Firewall | `github.com` | `osv-vulnerabilities.storage.googleapis.com`, `endoflife.date`, `www.cisa.gov` |
| Datenstand beim Scan | letzte Action (03:17 UTC) | Zeitpunkt der Aktualisierung |
| Nachvollziehbarkeit | Git-Historie der Daten | nur `stand.json` |
| Übernahme des GitHub-Repositorys | bei getrennten Daten: Daten fälschbar (falsche Ergebnisse), kein Code als root | ohne Folgen für die Daten |
| bei Ausfall | von GitHub/Action: Daten veralten (nach 3 Tagen Rückgabewert 2) | von OSV: Aktualisierung schlägt fehl |

Der Zeitgewinn beim direkten Abruf ist gering, wenn der Scan wie empfohlen einige Stunden nach der
Action läuft. Der direkte Weg lohnt sich vor allem, wenn der Server `github.com` nicht erreichen darf
oder GitHub auch als Datenquelle ausgeschlossen sein soll.

### Supportende (EOL)

`eol-daten.json` im Branch `daten` enthält einen Auszug aus [endoflife.date](https://endoflife.date) (MIT-Lizenz, siehe
[`EOL-LIZENZ.txt`](https://github.com/felixlohmeier/container-security-scan/blob/daten/EOL-LIZENZ.txt)), den die Action täglich aus dem vollständigen API-Export
(`/api/v1/products/full/`) erzeugt. Geprüft werden:

- **Pakete** mit npm-, Composer-, PyPI- oder Maven-Kennung bei endoflife.date (z. B. Laravel, Vue,
  Angular, jQuery, Bootstrap, Django, Drupal, TYPO3, Spring, Log4j) sowie ergänzend Symfony, CakePHP,
  Twig, Shopware, Craft CMS, Contao, Electron und Tomcat (`EOL_ZUSATZ` im Skript);
- **Laufzeiten und Server**, die nicht aus einem OS-Paket stammen (offizielle Images, Herstellerquellen):
  PHP/PHP-FPM, Node.js, Python, nginx, Apache httpd, MariaDB, MySQL, PostgreSQL. Stammen sie aus einem
  OS-Paket, zählt der Support der Distribution (Debian portiert Sicherheitskorrekturen zurück); deren
  Supportende wird über die Sicherheitsdaten erkannt (Rückgabewert 2).

Verglichen werden nur numerische Versionszweige (`2.7.16` → Zweig `2.7`, sonst `2`). Ein abgelaufener
Zweig erscheint als **Warnung** „Supportende“, ein Zweig mit Supportende in den nächsten 90 Tagen als
„Supportende bald“ – im Bericht und auf der Konsole, **nicht** als CVE und ohne Einfluss auf den
Rückgabewert. Fehlende oder mindestens 30 Tage alte EOL-Daten werden ebenfalls als Warnung gemeldet.
Maßgeblich ist das reguläre Supportende, nicht kommerzieller Zusatzsupport (z. B. für PHP oder Node.js).
Ohne Git-Checkout oder mit `--db DIR` lädt `--db-aktualisieren` die EOL-Daten direkt nach
`osv-db/eol-daten.json` bzw. `DIR/eol-daten.json`.

### Aktiv ausgenutzte Lücken (KEV)

`kev.json` im Branch `daten` enthält aus dem [Katalog der CISA](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
(Known Exploited Vulnerabilities, CC0) je CVE das Datum der Aufnahme; die Action lädt ihn täglich. Funde mit
einer dieser CVEs sind im Bericht mit `KEV` markiert, stehen auch als P3/P4 in der Tabelle und sind
**immer relevant** (Rückgabewert 1), unabhängig von Priorität und Schweregrad; `--nur-behebbare` gilt
auch für sie. Fehlende oder mindestens 7 Tage alte KEV-Daten sind eine Warnung, kein Rückgabewert 2:
Die Bewertung nach Priorität und Schweregrad bleibt vollständig. Ohne Git-Checkout oder mit `--db DIR`
lädt `--db-aktualisieren` den Katalog direkt nach `DIR/kev.json`.

Ein Beispiel aus dem [Solr-Bericht](beispiele/scan_app-solr_20261105_085231.md): libbrotli1
CVE-2026-111497 (HIGH laut Ubuntu, Paket nicht geladen, also P4). Ohne KEV nie gemeldet; laut CISA wird
die Lücke aktiv ausgenutzt.

## Rein lesend und ohne Datenabfluss

- Im Container laufen nur: `find`/`tar` (Metadaten-Dateien lesen; Container-Dateisystem und Volumes,
  nicht eingebundene Host-Verzeichnisse wie `/var/lib/docker`), ein POSIX-sh-Skript, das `/proc` liest –
  je Prozess-Benutzer, da Docker auch root im Container keinen Zugriff auf fremde Prozesse gibt –, und
  Versionsabfragen der gefundenen Programme (`node -e`, `php -r`, `python -I -S -c`, `java -version` …)
  mit Zeitlimit, im Verzeichnis `/` und **nie mit mehr Rechten als der laufende Prozess**.
- Die Konfiguration der Webserver (`nginx -T`, `apache2 -S/-M/-t`) wird mit dem Benutzer des jeweiligen
  Hauptprozesses abgefragt, nicht als root: Programm, Optionen und Konfiguration bestimmt der Container,
  und `load_module`/`LoadModule` würde dabei Code laden. Für einen Proxy direkt auf dem Host ebenso
  (`setpriv` mit Benutzer und Gruppe des Hauptprozesses, leere Umgebung, fester Suchpfad). `nginx -T` kann wie `nginx -t` fehlende Log- oder
  Temp-Verzeichnisse anlegen, die der Hauptprozess ohnehin anlegt.
- Befehle im Container (`sh`, `find`, `tar`, `awk`, `rpm` …) werden über einen festen Suchpfad
  (`/usr/sbin:/usr/bin:/sbin:/bin`) gesucht, nicht über den `PATH` des Images – liegt dort ein Verzeichnis,
  in das die Anwendung schreiben darf (z. B. ein venv), könnte sie sonst ein `sh` unterschieben, das der
  Scan als root startet. Nur `node`, `php`, `python3` … ohne Pfad werden über den `PATH` des Images
  gesucht, dann aber als `nobody` abgefragt.
- Ohne Shell oder Werkzeuge im Container wird passiv gelesen (`docker export`, `docker cp`, `/proc` des Hosts).
- Der tar-Strom aus dem Container wird im Speicher gelesen; nichts wird auf dem Host entpackt.
- Getestet: `docker diff` zeigt vor und nach dem Scan keine Änderung im Container.
- Es werden nur Daten **heruntergeladen** (GitHub bzw. OSV, endoflife.date und CISA); Paketlisten verlassen den Server nicht.
- Berichte und SBOM enthalten Kommandozeilen der Prozesse (oft mit Passwörtern) und Konfigurationsauszüge;
  das Skript legt sie daher nur für den aufrufenden Benutzer lesbar an (`umask 077`).

## Grenzen

- Schweregrad: Einstufung der Distribution (Debian, Ubuntu), sonst Angabe der Quelle, sonst CVSS 3 bzw.
  eine Näherung für CVSS 4 (eher zu hoch), sonst die Bewertung derselben CVE aus Bitnami/Alpine (`*`). Als
  Schadsoftware gemeldete Pakete (`MAL-…`) gelten als CRITICAL. Einträge, für die es nirgends eine Bewertung
  gibt („UNKNOWN“), zählen nicht als relevant (außer KEV), werden aber eigens ausgewiesen.
- Lücken nur unter Windows werden nur erkannt, wenn der Titel es eindeutig sagt; sonst Ausnahmeliste.
- Nicht erfasst: Rust, Ruby, .NET, Tcl, Programme ohne Versionskennung, Bundles ohne Kopfkommentar,
  Programme direkt auf dem Host, UDP-Dienste nur bei offenem Socket.
- Erreichbarkeit: Konfigurationen werden nur von nginx und Apache ausgewertet; andere Proxys machen alle
  Container in ihren Docker-Netzen „möglicherweise“ erreichbar (eher zu viel), auf dem Host alle Container.
  Ziele einer Anwendung, die selbst weiterleitet (API-Gateway), werden nur über Ziel-URLs in Umgebung bzw.
  Kommandozeile und über beim Scan offene Verbindungen erkannt – nicht über URLs, die nur in
  Konfigurationsdateien stehen (z. B. Spring `application.yml`), wenn gerade keine Verbindung besteht.
  Umgekehrt zählt auch ein interner HTTP-Dienst, den eine erreichbare App nur aufruft (eher zu viel).
- EOL-Abgleich nur für Produkte mit Paketkennung bzw. die genannten Laufzeiten/Server und nur für
  numerische Versionszweige; einzelne OS-Pakete, Java-Laufzeiten (herstellerabhängig) und Anwendungen
  ohne Paketkennung (z. B. WordPress, Nextcloud) werden nicht auf Supportende geprüft.
- Herstellerpaketquellen werden über typische Versionskennungen und Paketbetreuer erkannt
  (nginx.org, NodeSource, Sury, mariadb.org, PostgreSQL); andere Fremdquellen können unerkannt bleiben.
- Ein Einzelscan (ohne `--alle-container`/`--oeffentliche`) kennt keine Proxys in *anderen* Containern;
  Backends erscheinen dann als P2.
- nginx-Konfiguration: `nginx -T` wird mit `-p`/`-c` des laufenden Masterprozesses aufgerufen. Schlägt
  die Abfrage fehl (ebenso `apache2 -S` bzw. `-t -D DUMP_INCLUDES`), ist die Prüfung unvollständig
  (Rückgabewert 2), da Proxy-Backends fehlen könnten.

## Validierung

Getestet mit Python 3.6 und 3.13 (auch `LANG=C`) an Debian-, Ubuntu-, Alpine-, openSUSE- und
distroless-Containern (PHP/Apache, PHP-FPM, Node, Python, nginx, Solr, MariaDB), dazu eine unabhängige
Code-Prüfung mit gezielten Fehlerfällen (fehlende Werkzeuge im Container, Benutzerwechsel, venv über PATH,
`${APACHE_DOCUMENT_ROOT}`, nginx.org-Pakete, präparierte Module im Arbeitsverzeichnis, docker nicht
erreichbar). Abgleich mit Trivy (Image-Scan derselben Images, gleiche Datenstände):

- Paketerkennung: gleich (außer `gpg-pubkey`-Einträgen bei RPM, die keine Software sind).
- Schwachstellen: Trivy fand nichts, was das Skript nicht fand – bis auf Debians vorläufige
  `TEMP-…`-Kennungen ohne CVE und einzelne tzdata-Meldungen. Mehr Funde vor allem bei eingebetteten
  JavaScript-Bibliotheken, bei Laufzeiten aus offiziellen Images und bei offenen Ubuntu-CVEs ohne Fix.

Abgleich mit Grype 0.121 und Trivy 0.76 (11/2026, 8 laufende Container: nginx als Proxy vor Node, Python
und PHP-FPM, PHP 8.3 mit Code im Volume, Node auf distroless, Solr, MariaDB; Funde je Container auf
CVE und Paket abgeglichen, Abweichungen einzeln geprüft):

| Befund | Skript | Grype | Trivy |
|---|---|---|---|
| nginx von nginx.org, MariaDB von mariadb.org (Herstellerquellen), Java-Laufzeit | ✓ | – | – |
| Laufzeiten aus offiziellen Images (Node, PHP, Python) | ✓ | ✓ | – |
| Composer/npm im Volume | ✓ | nur über Syft mit Image-Katalogen | ✓ |
| eingebettetes jQuery | ✓ | – | – |
| Go-Standardbibliothek in `gosu` | ✓ (Schweregrad über die CVE) | teilweise | ✓ |
| Alpine curl 8.12.1: Lücken erst ab 8.13.0 | richtig nicht gemeldet | Fehlalarm | Fehlalarm |
| Alpine openssl/libxml2 mit zurückportiertem Fix | ✓ (seit [Versionsbereiche](#bewertung-der-funde)) | ✓ | ✓ |
| Kernel-Header `linux-libc-dev` | nicht geprüft | nicht geprüft | über 90 % der Funde |
| aktiv ausgenutzt (KEV) | ✓ | ✓ | – |

Grype eignet sich als unabhängige Zweitmeinung: andere Datenquellen (NVD, GitHub, Hersteller) als OSV.

## Entwicklung und Tests

Zum Ausprobieren und Entwickeln, **nur auf einem eigenen Testrechner** – auf Servern gilt
[Installation und Betrieb](#installation-und-betrieb):

```bash
git clone https://github.com/felixlohmeier/container-security-scan.git && cd container-security-scan
./container-security-scan.py --db-aktualisieren        # Branch daten nach daten/ holen (nicht als root)
sudo ./container-security-scan.py --alle-container berichte/ --nur-behebbare
```

```bash
python3 -m unittest discover -s tests                                   # Unit-Tests, ohne Docker (ca. 1 s)
./container-security-scan.py --db-aktualisieren                       # Daten (Branch daten) für den Docker-Test
CSS_DOCKER_TESTS=1 python3 -m unittest discover -s tests -p test_docker.py   # mit echten Containern
```

| Datei | Prüft |
|---|---|
| `test_versionen.py` | Versionsvergleiche (dpkg, rpm, apk, SemVer, PEP 440, Maven, PHP) und OSV-Versionsbereiche |
| `test_schweregrad.py` | CVSS 3/4, Vorrang von Quellen-Einstufung, Debian-Dringlichkeit, Ubuntu-Priorität, `MAL-…` |
| `test_inventar.py` | dpkg (auch distroless), apk, rpm, npm/Composer/PyPI, JS-Bibliotheken, JARs, Go-Build-Info, tar-Strom |
| `test_prozesse.py` | Prozesse, Ports und Dateien aus `/proc` (je Prozess-Benutzer bzw. über den Host, nie alle Host-Prozesse), Volumes, fester Suchpfad im Container, Benutzer der Versionsabfragen |
| `test_webserver.py` | nginx-/Apache-Konfiguration, `nginx -T` mit `-p`/`-c` und dem Benutzer des Hauptprozesses (nie root für fremde Programme/Optionen), nginx-Variablen (`set`, `map`), veröffentlichte Ports, Backends, Docker-Netze (macvlan, geroutet, Host-Netzwerk, gemeinsamer Netzwerk-Namespace), Ziele aus Traefik-/Caddy-Labels, Proxys und Tunnel direkt auf dem Host (Erkennung, Benutzer der Abfrage, Ziele über Container-IP) |
| `test_nutzung.py` | Zuordnung Komponente → Dienst, Erreichbarkeit (auch „möglicherweise“ über nicht auswertbare Proxys, Ziel-URLs und offene Verbindungen, Datenbanken als Ziel ausgenommen), Priorität P1–P4 |
| `test_osv.py` | Abgleich je Ökosystem, Quellpakete, Fremdquellen über Bitnami, Datenformat, Kürzung der Ubuntu-Daten (gleiche Funde wie vollständig), inkrementelle Aktualisierung, ungültige Kennungen (kein Pfad) |
| `test_bewertung.py` | widersprüchliche Versionsbereiche der Distribution, Kernel-Pakete, Schweregrad über die CVE, KEV (Daten erzeugen, laden, markieren), Ausnahmeliste (Format, Rechte, Ablauf), nur Windows, Relevanz, gefährliche Einstellungen (`CONF-…`), öffentliche Dienste als root (auch userns-remap/rootless) |
| `test_eol.py` | EOL-Daten erzeugen, Supportende und Vorwarnung |
| `test_ausgabe.py` | Bericht, CycloneDX-SBOM, Gesamtlauf mit Rückgabewerten 0/1/2 und bekannten Funden, KEV macht P4 relevant, gefährliche Einstellungen ergeben 1 (auch ohne Schwachstellen, Ausnahme nach Containername), root-Dienst nur Warnung (auch über Proxy-Ziel, nicht bei Loopback), Ausnahme, Kernel-Pakete |
| `test_kommandozeile.py` | Aufruf als Programm: Optionen (auch mehrfaches `--db`), Reihenfolge und Weitergabe der Erreichbarkeit mit `--alle-container`/`--oeffentliche`, `--db-aktualisieren` als root abgelehnt, holt bzw. aktualisiert nur den Branch `daten` (nie den Code), `daten/` ohne Git bricht ab, Berichte nur für den Aufrufer lesbar, docker nicht erreichbar, fehlerhafte Ausnahmeliste und unerwartete Fehler → 2 |
| `test_docker.py` | mit den Daten aus dem Branch `daten` unter `daten/`, Lauf mit `--alle-container`: nginx (`-c`) als Proxy vor Node (direkt und über `set $backend`), Traefik mit Label-Ziel und Nachbar ohne Label, gemeinsamer Netzwerk-Namespace, interner Container, Gateway in Node mit Ziel-URL und offenen Verbindungen (zu Node und Redis), nginx direkt auf dem Host vor einer Container-IP (wenn nginx installiert ist); EOL-Warnungen, Berichte, `docker diff` unverändert |
| `test_installation.py` | Installscript aus dem README: Syntax (auch des eingebetteten Wrappers), Beispiele der Ausnahmeliste gültig (auskommentiert und aktiviert, mit `CONF-…`), Link auf das Release; mit `CSS_RELEASE_TESTS=1` und voller Git-Historie, ob `VERSION` und `SHA256` zum Release passen (siehe [Releases](#releases)) |

Die GitHub Action [`tests.yml`](.github/workflows/tests.yml) führt die Unit-Tests mit Python 3.6, 3.11, 3.13 und
3.14 (Python des Runners, mit dem auch die Daten erzeugt werden), den Docker-Test und die Prüfung des
Installscripts gegen die Releases aus.

### Releases

Server installieren nur Releases: Git-Tags `vX.Y.Z` auf `main`, deren Prüfsumme im Installscript steht
([Schritt 1](#1-einrichten)). Ein Release:

1. Im Installscript `VERSION` und `SHA256` (`sha256sum container-security-scan.py`) eintragen, ebenso die
   Version im Link „aktuell …“ darüber; per Pull Request nach `main`.
2. Nach dem Merge den Merge-Commit taggen (signiert, wenn möglich) und den Tag pushen:

   ```bash
   git tag -s v1.1.0 -m v1.1.0 <commit>
   ```

   ```bash
   git push origin v1.1.0
   ```

3. Auf GitHub ein Release zum Tag anlegen und darin die Änderungen nennen, vor allem alles, was Admins
   wissen müssen (neue Voraussetzungen, geänderte Rückgabewerte, neue Einstellungen im Installscript).

`test_installation.py` stellt in der Action sicher, dass README und Releases zusammenpassen: Gibt es den Tag
`VERSION` schon, müssen Prüfsumme und Installscript genau dem Stand des Tags entsprechen – eine Änderung am
Installscript braucht also eine neue Version. Gibt es ihn noch nicht (Release in Vorbereitung), muss die
Prüfsumme zum aktuellen Skript passen. Beim Push eines Tags muss `VERSION` dem Tag entsprechen.

### Repository auf GitHub (Rulesets)

Damit das Token des Workflows nur die Daten ändern kann, in den Einstellungen des Repositorys unter
*Settings → Rules → Rulesets* (bzw. *Settings → Actions*) einrichten:

| Ruleset bzw. Einstellung | Regeln | Wirkung |
|---|---|---|
| Branch `main` (Default branch) | *Restrict deletions*, *Block force pushes*, *Require a pull request before merging*, optional *Require status checks to pass* (Unit-Tests) und *Require signed commits*; keine Ausnahme (*Bypass list*) für GitHub Actions | Code ändert sich nur über einen Pull Request; das Token des Workflows kann `main` nicht beschreiben. |
| Branch `daten` | *Restrict deletions*, *Block force pushes* | Die Action committet weiter direkt; die Historie der Daten lässt sich nicht umschreiben. |
| Tags `v*` | *Restrict creations* (Ausnahme nur *Repository admin*), *Restrict updates*, *Restrict deletions* | Releases legt nur der Admin an; ein Tag lässt sich nicht verschieben oder löschen. Ein verschobener Tag fiele auch an der Prüfsumme auf. |
| *Actions → General → Workflow permissions* | *Allow GitHub Actions to create and approve pull requests* aus (Standard) | Der Workflow kann sich nicht über einen eigenen Pull Request nach `main` schreiben. |

Rulesets schützen gegen Versehen und gegen ein missbrauchtes Token des Workflows, **nicht** gegen eine
Übernahme des Kontos: Wer Admin-Rechte hat, kann sie abschalten. Deshalb installieren Server nur die Datei
mit der Prüfsumme aus dem Installscript, das der Admin geprüft hat, und aktualisieren nur nach Prüfung.

## Verwandte Werkzeuge

- [Trivy](https://trivy.dev), [Grype](https://github.com/anchore/grype),
  [OSV-Scanner](https://github.com/google/osv-scanner): Images, Dateisysteme, SBOMs; ohne Laufzeitkontext.
- [Vuls](https://github.com/future-architect/vuls): agentloser Scanner für Server, kann betroffene Prozesse zeigen.
- [Kubescape](https://kubescape.io) „Relevancy“: priorisiert nach tatsächlich geladenen Paketen (eBPF, Kubernetes).
