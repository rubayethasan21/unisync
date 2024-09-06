from flask import Flask, render_template, jsonify
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import re
import asyncio
from nio import AsyncClient, MatrixRoom, RoomMessageText
import requests  # Import the requests library


app = Flask(__name__)

# Define a function to send the final data to the Matrix server
def send_data_to_matrix_server():
    """Sends a POST request to the Matrix server."""
    url = "http://unifyhn.de/add_user_to_rooms"
    headers = {"Content-Type": "application/json"}
    data = {
        "user_id": "@demo_user_2:unifyhn.de",
        "rooms": [{"room_name": "DemoRoom101"}]
    }
    response = requests.post(url, json=data, headers=headers)
    return response

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

@app.route('/')
def index():
    response = send_data_to_matrix_server()
    # Print response status code
    print('Response Status Code:', response.status_code)

    # Print response text
    print('Response Content:', response.text)

    # Print response JSON content (if JSON response)
    try:
        print('Response JSON Content:', response.json())
    except ValueError:
        print('Response is not in JSON format')
    return render_template('index.html')

@app.route('/sync')
def sync():
    return render_template('login.html')

@app.route('/perform-sync')
def perform_sync():
    print('perform_sync method')
    try:
        browser, playwright = create_playwright_browser(headless=False)
        #browser, playwright = create_playwright_browser(headless=True)

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
                # all_email_column_data.append(
                #     {
                #         'course_name': course['name'],
                #         'emails': emails
                #     }
                # )

                all_email_column_data.append(
                    {
                        'course_name': course['name'],
                        'course_id': course['refId'],
                        'students': emails
                    }
                )


            except Exception as e:
                # If an error occurs, print it and continue with the next course
                print(f"An error occurred while processing course {course['name']}: {e}")
                continue

        #print('all_username_column_data', all_username_column_data)
        print('all_username_column_data', all_email_column_data)

        final_data = {
            "classrooms": all_email_column_data
        }

        print('final_data', final_data)




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
