from flask import Flask, send_from_directory, abort, render_template_string
import os

app = Flask(__name__)
DEMO_FOLDER = 'demos'

@app.route('/demos/')
def list_demos():
    """List all demo files"""
    try:
        files = os.listdir(DEMO_FOLDER)
        links = [f"<li><a href='/demos/{file}'>{file}</a></li>" for file in files]
        return f"<h1>Available Demos</h1><ul>{''.join(links)}</ul>"
    except FileNotFoundError:
        abort(404)

@app.route('/demos/<path:filename>')
def serve_demo(filename):
    """Serve demo files"""
    try:
        return send_from_directory(DEMO_FOLDER, filename)
    except FileNotFoundError:
        abort(404)

if __name__ == '__main__':
    os.makedirs(DEMO_FOLDER, exist_ok=True)
    print(f"Demo server starting on http://0.0.0.0:8000")
    print(f"Serving files from: {os.path.abspath(DEMO_FOLDER)}")
    app.run(host='0.0.0.0', port=8000, debug=False)
