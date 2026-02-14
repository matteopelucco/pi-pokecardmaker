# pi-pokecardmaker
Generatore di immagini PokeDon 

## Prerequisiti

## Setup e Installazione

Segui questi passaggi per configurare l'ambiente e installare le dipendenze.

### 1. Clona il Repository (Opzionale)
Se hai scaricato i file manualmente, salta questo passaggio. Altrimenti, clona il repository:
```bash
git clone https://github.com/tuo-utente/pi-pokecardmaker.git
cd pi-pokecardmaker
```

### 2. Crea l'Ambiente Virtuale
È una buona pratica isolare le dipendenze del progetto. Esegui questo comando nella cartella principale del progetto:
```bash
python -m venv .venv
```
Verrà creata una cartella `.venv`.

### 3. Attiva l'Ambiente Virtuale
Devi attivare l'ambiente ogni volta che apri un nuovo terminale per lavorare al progetto.

**Su Windows:**

*   **Opzione A (Consigliata - PowerShell):**
    Potrebbe essere necessario abilitare l'esecuzione degli script. Apri PowerShell **come Amministratore** ed esegui:
    ```powershell
    Set-ExecutionPolicy RemoteSigned -Scope Process
    ```
    Successivamente, nel tuo terminale standard (non per forza da amministratore), esegui:
    ```powershell
    .venv\Scripts\activate
    ```

*   **Opzione B (Alternativa Facile - Prompt dei comandi `cmd`):**
    ```cmd
    .venv\Scripts\activate.bat
    ```

**Su macOS / Linux:**
```bash
source .venv/bin/activate
```
Una volta attivato, vedrai `(.venv)` all'inizio della riga del tuo terminale.

### 4. Installa i Requisiti
Con l'ambiente virtuale attivo, installa tutte le librerie necessarie con un solo comando:
```bash
pip install -r requirements.txt
```

## 5. Configurazione
...

## 6. Avvio 
...

## 7. Struttura del Progetto

