import subprocess
import threading
from pathlib import Path


def stream_logs(process, name):
    for line in iter(process.stdout.readline, b""):
        print(f"[{name}]: {line.decode().strip()}")


def start_server(command, name):
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True
    )

    log_thread = threading.Thread(target=stream_logs, args=(process, name))
    log_thread.start()

    return process


def launch(next_port: int | None = None, fastapi_port: int | None = None):
    next_port = next_port or 3000
    fastapi_port = fastapi_port or 8000

    current_dir = Path(__file__).parent

    next_command = f"PORT={next_port} EVALUATION_API=http://localhost:{fastapi_port} node {current_dir}/client_build/server.js"
    fastapi_command = f"uvicorn --app-dir {current_dir} server:app --host 0.0.0.0 --port {fastapi_port}"

    next_process = start_server(next_command, "Next.js Server")
    fastapi_process = start_server(fastapi_command, "FastAPI Server")

    next_process.wait()
    fastapi_process.wait()
