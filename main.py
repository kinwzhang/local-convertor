import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=app.config["BIND_HOST"],
        port=app.config["BIND_PORT"],
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
