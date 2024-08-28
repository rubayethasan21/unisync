from flask import Flask, render_template, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def create_selenium_browser():
    """Creates and returns a Selenium browser instance using Chromium."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--no-sandbox")  # Required to avoid issues in some environments
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems

    # Specify the ChromeDriver version using the install method
    service = Service(ChromeDriverManager().install())

    # Create the browser instance
    browser = webdriver.Chrome(service=service, options=options)
    return browser

def navigate_to_login_page(browser):
    """Navigates to the OpenID login page."""
    login_url = ('https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth'
                 '?response_mode=form_post&response_type=id_token&redirect_uri=https%3A%2F%2Filias.hs-heilbronn.de%2Fopenidconnect.php'
                 '&client_id=hhn_common_ilias&nonce=badc63032679bb541ff44ea53eeccb4e&state=2182e131aa3ed4442387157cd1823be0&scope=openid+openid')
    browser.get(login_url)
    print("Please log in manually in the opened browser window...")

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

def extract_username_column_from_table(html_content):
    """Extracts the username column (Anmeldename) from the table in the provided HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the table by class
    table = soup.find('table', {'class': 'table table-striped fullwidth'})

    # List to hold the username data
    username_column_data = []

    # Loop through all rows in the table body
    for row in table.find('tbody').find_all('tr'):
        # Get all columns (td elements)
        columns = row.find_all('td')
        if len(columns) >= 3:  # Ensure there are at least 3 columns
            username_column_data.append(columns[2].text.strip())  # Extract the text from the third column

    return username_column_data

def visit_course_page_and_scrape(browser, course):
    """Creates a dynamic URL for each course, navigates to it, and scrapes the content."""
    dynamic_url = f"https://ilias.hs-heilbronn.de/ilias.php?baseClass=ilrepositorygui&cmdNode=yc:ml:95&cmdClass=ilCourseMembershipGUI&ref_id={course['refId']}"
    print(f"Visiting dynamic URL: {dynamic_url}")
    browser.get(dynamic_url)

    course_html_content = browser.page_source
    print(f"Scraped HTML for {course['name']} at {dynamic_url}:", course_html_content)

    # Extract the usernames (Anmeldename) from the table
    usernames = extract_username_column_from_table(course_html_content)
    print(f"Username Column Data (Anmeldename) for {course['name']}:", usernames)

    return course_html_content, usernames

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sync')
def sync():
    return render_template('login.html')

@app.route('/perform-sync')
def perform_sync():
    try:
        browser = create_selenium_browser()

        navigate_to_login_page(browser)
        # Assuming the user logs in manually; no automated wait is needed here.

        # After login, you should add a way to ensure the browser has redirected to the correct page.
        # Example of waiting for a specific element to appear can be added here using WebDriverWait.

        # Manually navigate to the main courses page
        target_url = 'https://ilias.hs-heilbronn.de/ilias.php?cmdClass=ilmembershipoverviewgui&cmdNode=jr&baseClass=ilmembershipoverviewgui'
        browser.get(target_url)

        html_content = browser.page_source
        courses = extract_courses(html_content)
        print('Extracted Courses:', courses)

        all_username_column_data = []
        for course in courses:
            course_html_content, usernames = visit_course_page_and_scrape(browser, course)
            all_username_column_data.append({
                'course_name': course['name'],
                'user_name': usernames
            })

        print('all_username_column_data', all_username_column_data)
        browser.quit()

        # Render the result.html template with the data
        return render_template('result.html', all_username_column_data=all_username_column_data)

    except Exception as e:
        if 'browser' in locals():
            browser.quit()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
