from flask import Flask, render_template, jsonify
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import re
from nio import AsyncClient, LoginResponse
import asyncio

app = Flask(__name__)

# Matrix configuration
MATRIX_SERVER = "https://matrix.org"  # Replace with your Matrix server URL
MATRIX_USERNAME = "@yourusername:matrix.org"  # Replace with your Matrix username
MATRIX_PASSWORD = "yourpassword"  # Replace with your Matrix password

# Initialize the Matrix client
matrix_client = AsyncClient(MATRIX_SERVER, MATRIX_USERNAME)

def create_playwright_browser(headless=False):
    """Creates and returns a Playwright browser instance."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    return browser, playwright

def create_playwright_browser1(headless=False):
    """Creates and returns a Playwright browser instance."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(executable_path='/usr/bin/chromium-browser', headless=headless)
    return browser, playwright

def navigate_to_login_page(page):
    """Navigates to the OpenID login page."""
    login_url = ('https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth'
                 '?response_mode=form_post&response_type=id_token&redirect_uri=https%3A%2F%2Filias.hs-heilbronn.de%2Fopenidconnect.php'
                 '&client_id=hhn_common_ilias&nonce=badc63032679bb541ff44ea53eeccb4e&state=2182e131aa3ed4442387157cd1823be0&scope=openid+openid')
    page.goto(login_url)
    print("Please log in manually in the opened browser window...")

def wait_for_dashboard(page):
    """Waits until redirected to the dashboard after login."""
    try:
        page.wait_for_url("**/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
                          timeout=60000)  # Wait up to 60 seconds
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

def extract_email_column_from_table(html_content):
    """Extracts the email column (Anmeldename) from the table in the provided HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the table by class
    table = soup.find('table', {'class': 'table table-striped fullwidth'})

    # List to hold the username data
    email_column_data = []

    # Loop through all rows in the table body
    for row in table.find('tbody').find_all('tr'):
        # Get all columns (td elements)
        columns = row.find_all('td')
        if len(columns) >= 5:  # Ensure there are at least 5 columns
            email_column_data.append(columns[4].text.strip())  # Extract the text from the fifth column

    return email_column_data

def visit_course_page_and_scrape(page, course):
    """Creates a dynamic URL for each course, navigates to it, and scrapes the content."""
    dynamic_url = f"https://ilias.hs-heilbronn.de/ilias.php?baseClass=ilrepositorygui&cmdNode=yc:ml:95&cmdClass=ilCourseMembershipGUI&ref_id={course['refId']}"
    print(f"Visiting dynamic URL: {dynamic_url}")
    page.goto(dynamic_url)

    course_html_content = page.content()
    print(f"Scraped HTML for {course['name']} at {dynamic_url}:", course_html_content)

    # Extract the usernames (Anmeldename) from the table
    #usernames = extract_username_column_from_table(course_html_content)
    #print(f"Username Column Data (Anmeldename) for {course['name']}:", usernames)
    #return course_html_content, usernames

    emails = extract_email_column_from_table(course_html_content)
    print(f"Email Column Data for {course['name']}:", emails)

    return course_html_content, emails

# ========== Matrix Integration ========== #

async def matrix_login():
    """Handles login to the Matrix server."""
    if not matrix_client.logged_in:
        response = await matrix_client.login(MATRIX_PASSWORD)
        if not isinstance(response, LoginResponse):
            raise Exception("Matrix login failed")

async def create_room_and_add_members(course_name, emails):
    """Creates a room with the course_name and adds the emails as members."""
    try:
        await matrix_login()

        # Create a new room with the course name as the room name
        create_room_response = await matrix_client.room_create(
            name=course_name,
            preset="public_chat",  # or "private_chat" depending on your needs
            visibility="private",  # or "public" depending on your needs
            invite=emails  # Invite all users when creating the room
        )

        if not create_room_response.room_id:
            raise Exception(f"Failed to create room for course {course_name}")

        room_id = create_room_response.room_id
        print(f"Room created: {course_name} with ID {room_id}")

        # Send an introductory message to the room
        await matrix_client.room_send(
            room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": f"Welcome to the course room for {course_name}!"}
        )

        return room_id

    except Exception as e:
        print(f"Error creating room or adding members for course {course_name}: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sync')
def sync():
    return render_template('login.html')

@app.route('/perform-sync')
def perform_sync():
    try:
        browser, playwright = create_playwright_browser(headless=False)
        page = browser.new_page()

        navigate_to_login_page(page)
        wait_for_dashboard(page)
        navigate_to_main_courses_page(page)

        html_content = page.content()
        courses = extract_courses(html_content)
        print('Extracted Courses:', courses)

        #all_username_column_data = []
        all_email_column_data = []
        for course in courses:
            try:
                # course_html_content, usernames = visit_course_page_and_scrape(page, course)
                # all_username_column_data.append({
                #     'course_name': course['name'],
                #     'user_name': usernames
                # })

                course_html_content, emails = visit_course_page_and_scrape(page, course)
                all_email_column_data.append({
                    'course_name': course['name'],
                    'emails': emails
                })

                # Create Matrix room and add members
                room_id = asyncio.run(create_room_and_add_members(course['name'], emails))
                if room_id:
                    print(f"Successfully created room {course['name']} with ID {room_id}")

            except Exception as e:
                # If an error occurs, print it and continue with the next course
                print(f"An error occurred while processing course {course['name']}: {e}")
                continue

        #print('all_username_column_data', all_username_column_data)
        print('all_email_column_data', all_email_column_data)
        browser.close()
        playwright.stop()

        # Render the result.html template with the data
        #return render_template('result.html', all_username_column_data=all_username_column_data)
        return render_template('result.html', all_email_column_data=all_email_column_data)

    except Exception as e:
        if 'browser' in locals():
            browser.close()
        if 'playwright' in locals():
            playwright.stop()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
