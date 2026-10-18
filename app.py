import os
from flask import Flask, request, jsonify
import requests
from pyezvizapi.client import EzvizClient

app = Flask(__name__)

# Todas estas variables se configuran en Render, NUNCA se escriben acá directamente.
EZVIZ_EMAIL = os.environ["EZVIZ_EMAIL"]
EZVIZ_PASSWORD = os.environ["EZVIZ_PASSWORD"]
EZVIZ_REGION = os.environ.get("EZVIZ_REGION", "apiieu.ezvizlife.com")
DEVICE_SERIAL = os.environ["DEVICE_SERIAL"]
CAMERA_CHANNEL = int(os.environ.get("CAMERA_CHANNEL", "1"))
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
SECRET_KEY = os.environ["SECRET_KEY"]


@app.route("/snapshot")
def snapshot():
    # Protege el endpoint: sin la key correcta, nadie puede activar tu cámara.
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "unauthorized"}), 401

    tmp_path = "/tmp/snapshot.jpg"

    client = EzvizClient(account=EZVIZ_EMAIL, password=EZVIZ_PASSWORD, url=EZVIZ_REGION)
    try:
        client.login()
        client.save_image(DEVICE_SERIAL, tmp_path, channel=CAMERA_CHANNEL)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    with open(tmp_path, "rb") as f:
        image_bytes = f.read()

    try:
        requests.put(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=image_bytes,
            headers={
                "Filename": "estacionamiento.jpg",
                "Title": "Camara estacionamiento",
            },
            timeout=20,
        )
    except Exception as e:
        return jsonify({"error": f"foto ok, pero fallo el envio: {e}"}), 500

    return jsonify({"status": "ok"})


def fmt_pesos(n):
    # 1535 -> "$1.535" (formato argentino)
    return "$" + f"{n:,.0f}".replace(",", ".")


@app.route("/dolar")
def dolar():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "unauthorized"}), 401

    # Ej: /dolar?key=...&tipos=blue,oficial,bolsa   (por defecto: blue y oficial)
    tipos = request.args.get("tipos", "blue,oficial").split(",")
    nombres = {
        "oficial": "Oficial",
        "blue": "Blue",
        "bolsa": "MEP",
        "contadoconliqui": "CCL",
        "tarjeta": "Tarjeta",
        "mayorista": "Mayorista",
        "cripto": "Cripto",
    }

    try:
        resp = requests.get("https://dolarapi.com/v1/dolares", timeout=15)
        resp.raise_for_status()
        cotizaciones = {d["casa"]: d for d in resp.json()}
    except Exception as e:
        return jsonify({"error": f"no pude obtener la cotizacion: {e}"}), 500

    lineas = []
    for t in tipos:
        t = t.strip()
        d = cotizaciones.get(t)
        if d:
            lineas.append(
                f"{nombres.get(t, t)}: compra {fmt_pesos(d['compra'])} / venta {fmt_pesos(d['venta'])}"
            )

    if not lineas:
        return jsonify({"error": "tipo de dolar no encontrado"}), 400

    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data="\n".join(lineas).encode("utf-8"),
            headers={"Title": "Dolar hoy"},
            timeout=20,
        )
    except Exception as e:
        return jsonify({"error": f"fallo el envio: {e}"}), 500

    return jsonify({"status": "ok", "enviado": lineas})


@app.route("/")
def home():
    return "Servidor activo. Usa /snapshot?key=TU_CLAVE para pedir una foto."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
