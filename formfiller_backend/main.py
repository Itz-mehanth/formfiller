from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import random
import time
import threading
import queue
import logging

# --- Basic Setup ---
app = Flask(__name__)
CORS(app)

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Global State Management ---
automation_status = {
    'status': 'idle', 'message': 'Ready to start', 'progress': None,
    'successful': 0, 'total': 0
}
status_lock = threading.Lock()
stop_event = threading.Event()


class FormAnalyzer:
    """
    Analyzes a Google Form to extract various question types using BeautifulSoup.
    This version includes the fix for all known question types, including the latest linear scale HTML.
    """
    def __init__(self):
        self.driver = None

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless"); options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage"); options.add_argument("--disable-gpu")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)

    def analyze_form(self, form_url):
        self.setup_driver()
        try:
            self.driver.get(form_url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="list"]')))
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            questions = []
            question_containers = soup.find_all('div', class_='Qr7Oae') # A more stable container class

            for i, container in enumerate(question_containers):
                title_element = container.find('div', role='heading')
                if not title_element or not title_element.text.strip(): continue
                title = title_element.text.strip()
                question_data = {'title': title, 'index': i, 'type': 'unknown'}

                checkbox_elements = container.find_all('div', role='checkbox')
                radio_group = container.find('div', role='radiogroup')

                if container.find('input', type='text'):
                    question_data['type'] = 'short_answer'
                    question_data['answer_pool'] = ["Default Answer"]
                elif container.find('textarea'):
                    question_data['type'] = 'paragraph'
                    question_data['answer_pool'] = ["Default paragraph answer."]
                elif checkbox_elements:
                    question_data['type'] = 'multiple_choice_checkbox'
                    options = [{'text': cb.get('data-answer-value'), 'percentage': 50} for cb in checkbox_elements if cb.get('data-answer-value')]
                    question_data['options'] = options
                
                # --- START OF THE FIX ---
                # This logic now correctly identifies the linear scale by its 'radiogroup' role
                # and finds the clickable 'radio' divs within it.
                elif radio_group:
                    question_data['type'] = 'linear_scale'
                    scale_options = radio_group.find_all('div', role='radio')
                    percentage = 100 / len(scale_options) if scale_options else 100
                    options = []
                    for opt in scale_options:
                        value = opt.get('data-value')
                        if value:
                            options.append({'text': f'Scale {value}', 'value': value, 'percentage': percentage})
                    question_data['options'] = options
                # --- END OF THE FIX ---

                elif container.find_all('div', role='radio'):
                    question_data['type'] = 'multiple_choice_radio'
                    option_labels = container.find_all(class_='docssharedWizToggleLabeledContainer')
                    percentage = 100 / len(option_labels) if option_labels else 100
                    question_data['options'] = [{'text': label.text.strip(), 'percentage': percentage} for label in option_labels if label.text.strip()]
                
                if question_data['type'] != 'unknown':
                     questions.append(question_data)

            return questions
        except Exception as e:
            logger.error(f"Form analysis error: {e}", exc_info=True)
            return None
        finally:
            if self.driver: self.driver.quit()


class CustomFormFiller:
    """(This class remains unchanged as its logic is already correct)"""
    def __init__(self, thread_id, questions, form_url):
        self.thread_id = thread_id; self.questions = questions
        self.form_url = form_url; self.driver = None

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless"); options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage"); options.add_argument("--disable-gpu")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        self.driver = webdriver.Chrome(options=options)

    def fill_form(self):
        self.setup_driver()
        try:
            self.driver.get(self.form_url)
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'form')))
            for question in self.questions:
                q_type = question.get('type')
                try:
                    if q_type == 'multiple_choice_radio' or q_type == 'linear_scale':
                        self.select_radio_or_scale(question)
                    elif q_type == 'multiple_choice_checkbox':
                        self.select_checkboxes(question)
                    elif q_type == 'short_answer' or q_type == 'paragraph':
                        self.fill_text_area(question)
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Could not fill question '{question['title']}': {e}")
            return self.submit_form()
        except Exception as e:
            logger.error(f"Critical error during form filling: {e}", exc_info=True)
            return False
        finally:
            if self.driver: self.driver.quit()

    def select_radio_or_scale(self, question):
        options = question.get('options', [])
        if not options: return
        rand = random.uniform(0, 100); cumulative = 0
        selected_option = options[0]
        for option in options:
            cumulative += option.get('percentage', 0)
            if rand <= cumulative: selected_option = option; break
        
        selector_text = selected_option['value'] if question['type'] == 'linear_scale' else selected_option['text']
        # This XPath is robust enough to find the radio button by its data-value, which works for this new structure
        element_xpath = f"//div[@role='radio' and @data-value='{selector_text}']"
        element = self.driver.find_element(By.XPATH, element_xpath)
        self.driver.execute_script("arguments[0].click();", element)

    def select_checkboxes(self, question):
        options = question.get('options', [])
        for option in options:
            if random.uniform(0, 100) < option.get('percentage', 50):
                try:
                    element = self.driver.find_element(By.XPATH, f"//div[@data-answer-value=\"{option['text']}\"]")
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(0.2)
                except NoSuchElementException: logger.warning(f"Checkbox with text '{option['text']}' not found.")

    def fill_text_area(self, question):
        answer_pool = question.get('answer_pool', [])
        if not answer_pool: logger.warning(f"No answer pool for question: '{question['title']}'"); return
        answer = random.choice(answer_pool)
        try:
            title_element = self.driver.find_element(By.XPATH, f"//div[text()=\"{question['title']}\"]")
            text_input = title_element.find_element(By.XPATH, "./ancestor::div[@class='Qr7Oae']//input[@type='text'] | ./ancestor::div[@class='Qr7Oae']//textarea")
            text_input.send_keys(answer)
        except NoSuchElementException: logger.error(f"Could not find text input for question '{question['title']}'.")
    
    def submit_form(self):
        try:
            submit_button = self.driver.find_element(By.XPATH, '//div[@role="button" and .//span[text()="Submit"]]')
            submit_button.click()
            return True
        except Exception as e:
            logger.error(f"Failed to submit form: {e}"); return False

# --- Worker Thread and API Endpoints (remain unchanged) ---
def worker_thread(thread_id, num_forms, questions, form_url, delay, results_queue):
    successful_submissions = 0
    for i in range(num_forms):
        if stop_event.is_set(): break
        filler = CustomFormFiller(thread_id, questions, form_url)
        if filler.fill_form(): successful_submissions += 1
        with status_lock:
            automation_status['successful'] += 1 if successful_submissions > 0 else 0
            automation_status['message'] = f"Processing... {automation_status['successful']}/{automation_status['total']} completed"
        if i < num_forms - 1: time.sleep(delay + random.uniform(0, 1))
    results_queue.put(successful_submissions)

@app.route('/analyze-form', methods=['POST'])
def analyze_form_route():
    data = request.json; form_url = data.get('form_url')
    if not form_url or 'docs.google.com/forms' not in form_url: return jsonify({'success': False, 'error': 'A valid Google Forms URL is required'}), 400
    analyzer = FormAnalyzer(); questions = analyzer.analyze_form(form_url)
    if questions is None: return jsonify({'success': False, 'error': 'Failed to analyze the form.'}), 500
    if not questions: return jsonify({'success': False, 'error': 'No compatible questions were found.'}), 404
    return jsonify({'success': True, 'questions': questions})

@app.route('/start-automation', methods=['POST'])
def start_automation_route():
    stop_event.clear()
    data = request.json; form_url = data.get('form_url')
    questions = data.get('questions'); settings = data.get('settings', {})
    if not form_url or not questions: return jsonify({'success': False, 'error': 'Form URL and questions are required'}), 400
    total_submissions = int(settings.get('totalSubmissions', 50))
    num_threads = int(settings.get('threads', 1)); delay = int(settings.get('delay', 5))
    with status_lock:
        automation_status.update({'status': 'running', 'message': 'Initializing...','progress': True, 'successful': 0, 'total': total_submissions})
    def run_automation_background():
        results_queue = queue.Queue(); threads = []
        forms_per_thread = total_submissions // num_threads
        extra_forms = total_submissions % num_threads
        for i in range(num_threads):
            num_forms = forms_per_thread + (1 if i < extra_forms else 0)
            if num_forms > 0:
                thread = threading.Thread(target=worker_thread, args=(i + 1, num_forms, questions, form_url, delay, results_queue), name=f"Worker-{i+1}")
                threads.append(thread); thread.start()
        for thread in threads: thread.join()
        total_successful = sum(list(results_queue.queue))
        with status_lock:
            if stop_event.is_set():
                automation_status.update({'status': 'stopped', 'message': f'Process stopped. {total_successful}/{total_submissions} completed.'})
            else:
                automation_status.update({'status': 'completed', 'message': f'Automation completed! {total_successful}/{total_submissions} successful.'})
            automation_status['successful'] = total_successful
    automation_thread = threading.Thread(target=run_automation_background, name="AutomationManager")
    automation_thread.start()
    return jsonify({'success': True, 'message': 'Automation started.'})

@app.route('/stop-automation', methods=['POST'])
def stop_automation_route():
    logger.info("Stop request received."); stop_event.set()
    with status_lock:
        automation_status['status'] = 'stopping'
        automation_status['message'] = 'Stopping process...'
    return jsonify({'success': True, 'message': 'Stop signal sent.'})

@app.route('/automation-status', methods=['GET'])
def get_automation_status():
    with status_lock: return jsonify(automation_status)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    print("🚀 Google Forms Automation Server Starting...")
    print("📡 Server will run on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)