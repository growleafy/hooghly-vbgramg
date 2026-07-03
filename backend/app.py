import os
import json
import requests
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
from weasyprint import HTML
from datetime import datetime
import io

app = Flask(__name__)
CORS(app)  # Allow frontend to call this service

# Environment variables
NHOST_GRAPHQL_URL = os.environ.get('NHOST_GRAPHQL_URL', 'http://localhost:8080/v1/graphql')
NHOST_ADMIN_SECRET = os.environ.get('NHOST_ADMIN_SECRET', '')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')

# GraphQL client helper
def execute_graphql(query, variables=None):
    headers = {
        'Content-Type': 'application/json',
    }
    if NHOST_ADMIN_SECRET:
        headers['x-hasura-admin-secret'] = NHOST_ADMIN_SECRET
    
    payload = {'query': query}
    if variables:
        payload['variables'] = variables
    
    response = requests.post(NHOST_GRAPHQL_URL, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    if 'errors' in data:
        raise Exception(f"GraphQL errors: {data['errors']}")
    return data['data']

# GraphQL query to fetch multiple works by IDs
GET_WORKS_QUERY = """
query GetWorks($ids: [Int!]!) {
  permissible_works(where: {id: {_in: $ids}}) {
    id
    vb_gram_g_number
    name
    beneficiary_type
    description
    purpose
    technical_details
    expected_outcomes
    design_notes
    construction_guidelines
    repair_maintenance_guidelines
    restrictions
    eligibility
    remarks
    work_type {
      name
      sub_category {
        name
        master_category {
          name
        }
      }
    }
    work_images(order_by: {display_order: asc}) {
      image_url
      caption
    }
    scheme_work_mappings {
      scheme_component {
        component_name
        government_scheme {
          name
        }
      }
    }
  }
}
"""

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/generate-handbook', methods=['POST'])
def generate_handbook():
    """
    Expects JSON: { "work_ids": [1, 2, 3, ...] }
    Returns a PDF file.
    """
    data = request.get_json()
    if not data or 'work_ids' not in data:
        return jsonify({'error': 'Missing work_ids'}), 400
    
    work_ids = data['work_ids']
    if not work_ids:
        return jsonify({'error': 'work_ids cannot be empty'}), 400
    
    # Fetch work details from Hasura
    try:
        result = execute_graphql(GET_WORKS_QUERY, {'ids': work_ids})
        works = result.get('permissible_works', [])
    except Exception as e:
        return jsonify({'error': f'Failed to fetch works: {str(e)}'}), 500
    
    if not works:
        return jsonify({'error': 'No works found'}), 404
    
    # Build HTML content using Jinja2 template
    # (We'll embed the template inline for simplicity, but you can use a file)
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>VB-G RAM G Handbook</title>
        <style>
            body { font-family: 'Arial', sans-serif; padding: 40px; }
            h1 { color: #003366; border-bottom: 2px solid #003366; }
            h2 { color: #004080; margin-top: 30px; }
            .work-card { border: 1px solid #ddd; padding: 20px; margin-bottom: 30px; border-radius: 8px; }
            .work-number { background: #003366; color: white; padding: 4px 12px; border-radius: 20px; display: inline-block; }
            .beneficiary { background: #e6f0fa; padding: 2px 10px; border-radius: 20px; }
            .images { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0; }
            .images img { max-width: 200px; border: 1px solid #ccc; border-radius: 4px; }
            .schemes { background: #f5f5f5; padding: 10px; border-radius: 4px; }
            .footer { margin-top: 50px; border-top: 1px solid #ccc; padding-top: 20px; color: #666; }
        </style>
    </head>
    <body>
        <h1>Viksit Gram Darshika</h1>
        <p><strong>Generated on:</strong> {{ date }}</p>
        <p><strong>Total Works Selected:</strong> {{ works|length }}</p>
        
        {% for work in works %}
        <div class="work-card">
            <h2>
                <span class="work-number">#{{ work.vb_gram_g_number }}</span>
                {{ work.name }}
                <span class="beneficiary">{{ work.beneficiary_type }}</span>
            </h2>
            <p><strong>Category:</strong> {{ work.work_type.sub_category.master_category.name }}</p>
            <p><strong>Sub-category:</strong> {{ work.work_type.sub_category.name }}</p>
            <p><strong>Work Type:</strong> {{ work.work_type.name }}</p>
            
            {% if work.description %}
            <h3>Description</h3>
            <p>{{ work.description }}</p>
            {% endif %}
            
            {% if work.purpose %}
            <h3>Purpose</h3>
            <p>{{ work.purpose }}</p>
            {% endif %}
            
            {% if work.technical_details %}
            <h3>Technical Details</h3>
            <p>{{ work.technical_details }}</p>
            {% endif %}
            
            {% if work.expected_outcomes %}
            <h3>Expected Outcomes</h3>
            <p>{{ work.expected_outcomes }}</p>
            {% endif %}
            
            {% if work.work_images %}
            <h3>Reference Images</h3>
            <div class="images">
                {% for img in work.work_images %}
                <div>
                    <img src="{{ img.image_url }}" alt="{{ img.caption or 'Image' }}" />
                    <p><small>{{ img.caption or '' }}</small></p>
                </div>
                {% endfor %}
            </div>
            {% endif %}
            
            {% if work.scheme_work_mappings %}
            <h3>Related Schemes</h3>
            <div class="schemes">
                <ul>
                {% for mapping in work.scheme_work_mappings %}
                    <li>{{ mapping.scheme_component.government_scheme.name }} - {{ mapping.scheme_component.component_name }}</li>
                {% endfor %}
                </ul>
            </div>
            {% endif %}
        </div>
        {% endfor %}
        
        <div class="footer">
            <p>This handbook was automatically generated using the VB-G RAM G Digital Planning Portal.</p>
            <p>Ministry of Rural Development, Government of India</p>
        </div>
    </body>
    </html>
    """
    
    # Render HTML
    html_content = render_template_string(html_template, works=works, date=datetime.now().strftime('%d %B %Y'))
    
    # Generate PDF
    pdf_file = HTML(string=html_content, base_url='.').write_pdf()
    
    # Return as downloadable file
    return send_file(
        io.BytesIO(pdf_file),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'GP_Handbook_{datetime.now().strftime("%Y%m%d")}.pdf'
    )

# Optional: Excel export endpoint (similar structure)
@app.route('/api/generate-excel', methods=['POST'])
def generate_excel():
    # ... use openpyxl to generate .xlsx
    pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
