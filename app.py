from flask import Flask, render_template, request, jsonify, send_file, abort
import os
from main import process_objective

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    objective = request.form['objective']
    file_content = request.form.get('file_content', None)
    use_search = request.form.get('use_search', 'false') == 'true'

    result = process_objective(objective, file_content, use_search)
    
    # Update file paths to be relative to the current working directory
    result['log_file'] = os.path.join(result['project_name'], os.path.basename(result['log_file']))
    result['created_files'] = [os.path.join(result['project_name'], file) for file in result['created_files']]
    
    return jsonify(result)

@app.route('/download/<path:filename>')
def download_file(filename):
    try:
        file_path = os.path.join(os.getcwd(), filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            abort(404)
    except Exception as e:
        print(f"Error in download_file: {str(e)}")
        abort(500)

if __name__ == '__main__':
    app.run(debug=True)