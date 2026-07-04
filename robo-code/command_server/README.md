# Command Server

Polls the Mission Control backend for pending commands and executes them.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Server runs on `http://localhost:42001`

## How It Works

1. **Startup**: Creates a background polling task
2. **Polling**: Every 2 seconds, polls `http://localhost:42000/api/v1/commands/pending`
3. **Execution**: Executes commands and simulates device operations
4. **Acknowledgment**: Sends ACK back to backend to remove command from queue

## API Endpoints

**Status**
```
GET /api/v1/status
```

**Executed Commands History**
```
GET /api/v1/commands/executed
```

## File Structure

- `app.py` - FastAPI frontend and server setup
- `handler.py` - Command execution logic and backend communication
- `requirements.txt` - Dependencies

## Notes

- Polls backend every 2 seconds (configurable in `handler.start_polling()`)
- Currently simulates device execution (logs to console)
- Ready to integrate with actual device interfaces
