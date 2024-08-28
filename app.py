from flask import Flask, render_template, jsonify
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import re
import asyncio

app = Flask(__name__)

async def create_playwright_browser(headless=False):
    """Creates and returns a Playwright browser instance using the system-installed Chromium."""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        executable_path='/usr/bin/chromium',  # Use system-installed Chromium
        headless=headless
    )
    return browser, playwright

async def navigate_to_login_page(page):
    """Navigates to the OpenID login page."""
    login_url = ('https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth'
                 '?response_mode=form_post&response_type=id_token&redirect_uri=https%3A%2F%2Filias.hs-heilbronn.de%2Fopenidconnect.php'
                 '&client_id=hhn_common_ilias&nonce=badc63032679bb541ff44ea53eeccb4e&state=2182e131aa3ed4442387157cd1823be0&scope=openid+openid')
    await page.goto(login_url)
    print("Please log in manually in the opened browser window...")

async def wait_for_dashboard(page):
    """Waits until redirected to the dashboard after login."""
    try:
        await page.wait_for_url("**/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
                                timeout=60000)  # Wait up to 60 seconds
        print("Login successful. Redirecting to the target URL...")
    except PlaywrightTimeoutError:
        raise Exception("Login did not complete within the expected time.")

async def navigate_to_main_courses_page(page):
    """Navigates to the main courses page after logging in."""
    target_url = 'https://ilias.hs-heilbronn.de/ilias.php?cmdClass=ilmembershipoverviewgui&cmdNode=jr&baseClass=ilmembershipoverviewgui'
    await page.goto(target_url)

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

async def visit_course_page_and_scrape(page, course):
    """Creates a dynamic URL for each course, navigates to it, and scrapes the content."""
    dynamic_url = f"https://ilias.hs-heilbronn.de/ilias.php?baseClass=ilrepositorygui&cmdNode=yc:ml:95&cmdClass=ilCourseMembershipGUI&ref_id={course['refId']}"
    print(f"Visiting dynamic URL: {dynamic_url}")
    await page.goto(dynamic_url)

    course_html_content = await page.content()
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
async def perform_sync():
    try:
        browser, playwright = await create_playwright_browser(headless=False)
        page = await browser.new_page()

        await navigate_to_login_page(page)
        await wait_for_dashboard(page)
        await navigate_to_main_courses_page(page)

        html_content = await page.content()
        courses = extract_courses(html_content)
        print('Extracted Courses:', courses)

        all_username_column_data = []
        for course in courses:
            course_html_content, usernames = await visit_course_page_and_scrape(page, course)
            all_username_column_data.append({
                'course_name': course['name'],
                'user_name': usernames
            })

        print('all_username_column_data', all_username_column_data)
        await browser.close()
        await playwright.stop()

        # Render the result.html template with the data
        return render_template('result.html', all_username_column_data=all_username_column_data)

    except Exception as e:
        if 'browser' in locals():
            await browser.close()
        if 'playwright' in locals():
            await playwright.stop()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
