from flask import Flask, request, jsonify, send_file
import os, threading, uuid
import pipeline

app = Flask(__name__, static_folder="static")
jobs = {}

os.makedirs("outputs", exist_ok=True)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "starting", "clips": [], "error": None}
    t = threading.Thread(target=pipeline.run, args=(job_id, url, jobs))
    t.daemon = True
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join("outputs", filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
