from flask import Flask, render_template, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import os

app = Flask(__name__)


def create_selenium_browser(headless=False):
    """Creates and returns a Selenium WebDriver instance."""
    chrome_options = webdriver.ChromeOptions()
    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver


def navigate_to_login_page(driver):
    """Navigates to the OpenID login page."""
    login_url = ('https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth'
                 '?response_mode=form_post&response_type=id_token&redirect_uri=https%3A%2F%2Filias.hs-heilbronn.de%2Fopenidconnect.php'
                 '&client_id=hhn_common_ilias&nonce=badc63032679bb541ff44ea53eeccb4e&state=2182e131aa3ed4442387157cd1823be0&scope=openid+openid')

    driver.get(login_url)
    print(f"Navigated to login page, current URL: {driver.current_url}")

    # Take a screenshot for debugging
    screenshot_path = os.path.join(os.getcwd(), 'login_page_screenshot.png')
    driver.save_screenshot(screenshot_path)
    print(f"Screenshot saved at {screenshot_path}")

    if "login.hs-heilbronn.de" not in driver.current_url:
        raise Exception("Failed to navigate to the login page")


def wait_for_dashboard(driver):
    """Waits until redirected to the dashboard after login."""
    try:
        WebDriverWait(driver, 60).until(EC.url_contains("ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems"))
        print("Login successful. Redirecting to the target URL...")
    except Exception as e:
        raise Exception("Login did not complete within the expected time.")


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


def visit_course_page_and_scrape(driver, course):
    """Creates a dynamic URL for each course, navigates to it, and scrapes the content."""
    dynamic_url = f"https://ilias.hs-heilbronn.de/ilias.php?baseClass=ilrepositorygui&cmdNode=yc:ml:95&cmdClass=ilCourseMembershipGUI&ref_id={course['refId']}"
    print(f"Visiting dynamic URL: {dynamic_url}")
    driver.get(dynamic_url)

    course_html_content = driver.page_source
    print(f"Scraped HTML for {course['name']} at {dynamic_url}:", course_html_content)

    # Extract the emails from the table
    emails = extract_email_column_from_table(course_html_content)
    print(f"Email Column Data for {course['name']}:", emails)

    return course_html_content, emails


def extract_email_column_from_table(html_content):
    """Extracts the email column from the table in the provided HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the table by class
    table = soup.find('table', {'class': 'table table-striped fullwidth'})

    # List to hold the email data
    email_column_data = []

    # Loop through all rows in the table body
    for row in table.find('tbody').find_all('tr'):
        # Get all columns (td elements)
        columns = row.find_all('td')
        if len(columns) >= 5:  # Ensure there are at least 5 columns
            email_column_data.append(columns[4].text.strip())  # Extract the text from the fifth column

    return email_column_data


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/sync')
def sync():
    return render_template('sync.html')

    #return render_template('login.html')


@app.route('/perform-sync')
def perform_sync():
    print('Starting perform_sync method')
    try:
        # Set headless=True for production, False for testing/debugging
        driver = create_selenium_browser(headless=False)

        navigate_to_login_page(driver)
        wait_for_dashboard(driver)

        # Navigate to main courses page
        target_url = 'https://ilias.hs-heilbronn.de/ilias.php?cmdClass=ilmembershipoverviewgui&cmdNode=jr&baseClass=ilmembershipoverviewgui'
        driver.get(target_url)

        html_content = driver.page_source
        courses = extract_courses(html_content)
        print('Extracted Courses:', courses)

        # Collect email data
        all_email_column_data = []
        for course in courses:
            try:
                course_html_content, emails = visit_course_page_and_scrape(driver, course)
                all_email_column_data.append({
                    'course_name': course['name'],
                    'emails': emails
                })
            except Exception as e:
                print(f"An error occurred while processing course {course['name']}: {e}")
                continue

        print('Collected Email Data:', all_email_column_data)
        driver.quit()

        # Render the result template
        return render_template('result.html', all_email_column_data=all_email_column_data)

    except Exception as e:
        print(f"Error in perform_sync: {e}")
        if 'driver' in locals():
            driver.quit()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
