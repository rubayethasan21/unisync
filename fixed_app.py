from flask import Flask, render_template, jsonify, request, Response
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import re
import requests
import base64

app = Flask(__name__)

session_data = {}

def capture_screenshot(session_id):
    if not session_id in session_data:
        return None
    page = session_data[session_id].get("page")
    if page:
        session_data[session_id]['screenshot'] = page.screenshot()

def send_data_to_matrix_server(user_id, room_name):
    url = "http://unifyhn.de/add_user_to_rooms"
    headers = {"Content-Type": "application/json"}
    data = {
        "user_id": "@" + user_id + ":unifyhn.de",
        "rooms": [{"room_name": room_name}]
    }
    response = requests.post(url, json=data, headers=headers)
    return response

def create_playwright_browser(headless=True):
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    return browser, playwright

def navigate_to_login_page(page, username, password):
    login_url = ('https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth'
                 '?response_mode=form_post&response_type=id_token&redirect_uri=https%3A%2F%2Filias.hs-heilbronn.de%2Fopenidconnect.php'
                 '&client_id=hhn_common_ilias&nonce=badc63032679bb541ff44ea53eeccb4e&state=2182e131aa3ed4442387157cd1823be0&scope=openid+openid')
    page.goto(login_url)
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('input[name="login"]')
    print("Login credentials submitted. Waiting for OTP or dashboard...")


def wait_for_dashboard(page):
    """Waits until redirected to the dashboard after login."""
    try:
        page.wait_for_url("**/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
                          timeout=60000)  # Wait up to 60 seconds
        print("Login successful. Redirecting to the target URL...")
    except PlaywrightTimeoutError:
        raise Exception("Login did not complete within the expected time.")
    

def navigate_to_main_courses_page(page):
    target_url = 'https://ilias.hs-heilbronn.de/ilias.php?cmdClass=ilmembershipoverviewgui&cmdNode=jr&baseClass=ilmembershipoverviewgui'
    page.goto(target_url)

def extract_courses(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    courses = []

    def get_ref_id(url):
        match = re.search(r'ref_id=(\d+)', url)
        return match.group(1) if match else ''

    course_rows = soup.select('.il-std-item')
    for course_row in course_rows:
        img_element = course_row.select_one('img.icon')
        if img_element and img_element.get('alt') != 'Symbol Gruppe':
            course_name_element = course_row.select_one('.il-item-title a')
            if course_name_element:
                course_name = course_name_element.get_text(strip=True)
                course_url = course_name_element.get('href')
                course_ref_id = get_ref_id(course_url)
                courses.append({
                    'name': course_name,
                    'refId': course_ref_id,
                    'url': course_url,
                })

    return courses

def extract_email_column_from_table(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'class': 'table table-striped fullwidth'})
    email_column_data = []

    if table and table.find('tbody'):
        for row in table.find('tbody').find_all('tr'):
            columns = row.find_all('td')
            if len(columns) >= 5:
                email_column_data.append(columns[4].text.strip())

    return email_column_data

def visit_course_page_and_scrape(page, course):
    dynamic_url = f"https://ilias.hs-heilbronn.de/ilias.php?baseClass=ilrepositorygui&cmdNode=yc:ml:95&cmdClass=ilCourseMembershipGUI&ref_id={course['refId']}"
    print(f"Visiting dynamic URL: {dynamic_url}")
    page.goto(dynamic_url)

    course_html_content = page.content()
    emails = extract_email_column_from_table(course_html_content)
    print(f"Email Column Data for {course['name']}:", emails)

    return course_html_content, emails

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sync')
def sync():
    response = send_data_to_matrix_server('demo_user_1', 'DemoRoom500')
    print('Response Status Code:', response.status_code, flush=True)
    print('Response Content:', response.text, flush=True)
    try:
        print('Response JSON Content:', response.json(), flush=True)
    except ValueError:
        print('Response is not in JSON format', flush=True)
    return render_template('login.html')

@app.route('/perform-sync', methods=['GET'])
def perform_sync():
    username = request.args.get('username')
    password = request.args.get('password')
    
    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password are required"}), 400

    try:
        browser, playwright = create_playwright_browser(headless=True)
        page = browser.new_page()
        session_id = base64.urlsafe_b64encode(username.encode()).decode()
        session_data[session_id] = {
            'browser': browser,
            'page': page,
            'playwright': playwright,
            'screenshot': None
        }
        capture_screenshot(session_id)
        navigate_to_login_page(page, username, password)
        capture_screenshot(session_id)
        try: 
            page.wait_for_selector('input[name="otp"]', timeout=3000)
        except:
            cleanup_session(session_id)
            return jsonify({"status": "authentication_failed", "message": "Looks like you provided wrong details. Please try submitting again.", "session_id": session_id})
        return jsonify({"status": "otp_required", "session_id": session_id})
    except Exception as e:
        cleanup_session(session_id)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/submit-otp', methods=['POST'])
def submit_otp():
    otp = request.form.get('otp')
    session_id = request.form.get('session_id')

    if not otp or not session_id:
        return jsonify({"status": "error", "message": "OTP and session ID are required"}), 400

    if session_id not in session_data:
        return jsonify({"status": "error", "message": "Invalid session ID"}), 404

    try:
        page = session_data[session_id]['page']
        page.fill('input[name="otp"]', otp)
        capture_screenshot(session_id)
        page.click('button[type="submit"]')
        capture_screenshot(session_id)
        wait_for_dashboard(page)
        return process_courses(session_id)
    except Exception as e:
        cleanup_session(session_id)
        return jsonify({"status": "error", "message": str(e)}), 500

def process_courses(session_id):
    page = session_data[session_id]['page']
    navigate_to_main_courses_page(page)

    html_content = page.content()
    courses = extract_courses(html_content)
    print('Extracted Courses:', courses)

    all_email_column_data = []
    for course in courses:
        try:
            course_html_content, emails = visit_course_page_and_scrape(page, course)
            all_email_column_data.append({
                'course_name': course['name'],
                'course_id': course['refId'],
                'students': emails
            })
        except Exception as e:
            print(f"An error occurred while processing course {course['name']}: {e}")
            continue

    final_data = {"classrooms": all_email_column_data}
    print('final_data', final_data)

    cleanup_session(session_id)
    return jsonify({"status": "success", "data": final_data})

def cleanup_session(session_id):
    if session_id in session_data:
        session_data[session_id]['browser'].close()
        session_data[session_id]['playwright'].stop()
        del session_data[session_id]

@app.route('/screenshot/<session_id>')
def screenshot(session_id):
    if session_id not in session_data:
        return jsonify({"status": "error", "message": "Invalid session ID"}), 404

    try:
        screenshot = session_data[session_id]['screenshot']
        return Response(screenshot, mimetype='image/png')
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)