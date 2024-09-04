from flask import Flask, render_template, jsonify
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import re
import os
import hashlib
import uuid

app = Flask(__name__)

# Generate dynamic nonce and state values for security
def generate_nonce():
    return hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()

def generate_state():
    return hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()

def create_playwright_browser(headless=False):
    """Creates and returns a Playwright browser instance."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-gpu", "--no-sandbox", "--enable-logging", "--v=1"]
    )
    return browser, playwright

def navigate_to_login_page(page):
    """Navigates to the OpenID login page and logs the current page URL."""
    nonce = generate_nonce()
    state = generate_state()

    login_url = (f'https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth'
                 f'?response_mode=form_post&response_type=id_token&redirect_uri=https%3A%2F%2Filias.hs-heilbronn.de%2Fopenidconnect.php'
                 f'&client_id=hhn_common_ilias&nonce={nonce}&state={state}&scope=openid+openid')

    page.goto(login_url)
    print(f"Navigated to login page, current URL: {page.url}")

    # Take a screenshot for debugging
    screenshot_path = os.path.join(os.getcwd(), 'login_page_screenshot.png')
    page.screenshot(path=screenshot_path)
    print(f"Screenshot saved at {screenshot_path}")

    if "login.hs-heilbronn.de" not in page.url:
        raise Exception("Failed to navigate to the login page")

def wait_for_dashboard(page):
    """Waits until redirected to the dashboard after login."""
    try:
        page.wait_for_url("**/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
                          timeout=60000)  # Adjust timeout if needed
        print("Login successful. Redirecting to the target URL...")
    except PlaywrightTimeoutError:
        raise Exception("Login did not complete within the expected time.")

def navigate_to_main_courses_page(page):
    """Navigates to the main courses page after logging in."""
    target_url = 'https://ilias.hs-heilbronn.de/ilias.php?cmdClass=ilmembershipoverviewgui&cmdNode=jr&baseClass=ilmembershipoverviewgui'
    page.goto(target_url)

def extract_courses(html_content):
    """Extracts course information from the provided HTML content."""
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
    """Extracts the email column from the table in the provided HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')

    table = soup.find('table', {'class': 'table table-striped fullwidth'})

    email_column_data = []

    for row in table.find('tbody').find_all('tr'):
        columns = row.find_all('td')
        if len(columns) >= 5:
            email_column_data.append(columns[4].text.strip())

    return email_column_data

def visit_course_page_and_scrape(page, course):
    """Creates a dynamic URL for each course, navigates to it, and scrapes the content."""
    dynamic_url = f"https://ilias.hs-heilbronn.de/ilias.php?baseClass=ilrepositorygui&cmdNode=yc:ml:95&cmdClass=ilCourseMembershipGUI&ref_id={course['refId']}"
    print(f"Visiting dynamic URL: {dynamic_url}")
    page.goto(dynamic_url)

    course_html_content = page.content()
    print(f"Scraped HTML for {course['name']} at {dynamic_url}")

    emails = extract_email_column_from_table(course_html_content)
    print(f"Email Column Data for {course['name']}:", emails)

    return course_html_content, emails

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sync')
def sync():
    return render_template('login.html')

@app.route('/perform-sync')
def perform_sync():
    print('Starting perform_sync method')
    try:
        browser, playwright = create_playwright_browser(headless=False)  # Running in headed mode

        page = browser.new_page()

        print("Navigating to login page...")
        navigate_to_login_page(page)

        print("Waiting for dashboard...")
        wait_for_dashboard(page)

        print("Navigating to main courses page...")
        navigate_to_main_courses_page(page)

        html_content = page.content()
        courses = extract_courses(html_content)
        print('Extracted Courses:', courses)

        all_email_column_data = []
        for course in courses:
            try:
                print(f"Visiting course page: {course['name']}")
                course_html_content, emails = visit_course_page_and_scrape(page, course)
                all_email_column_data.append({
                    'course_name': course['name'],
                    'emails': emails
                })
            except Exception as e:
                print(f"An error occurred while processing course {course['name']}: {e}")
                continue

        print('All extracted email data:', all_email_column_data)

        browser.close()
        playwright.stop()

        return render_template('result.html', all_email_column_data=all_email_column_data)

    except Exception as e:
        print(f"Error during sync: {e}")
        if 'browser' in locals():
            browser.close()
        if 'playwright' in locals():
            playwright.stop()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
