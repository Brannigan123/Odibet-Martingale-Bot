from datetime import datetime, timedelta
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC

from pyautogui import confirm, prompt
from schedule import every, run_pending

from dateutil.parser import parse as parsedate
from time import sleep, struct_time
from sys import exit

import json
import pause

driver = webdriver.Firefox()
actions = ActionChains(driver)

# intercept requests at
driver.scopes = [
    'https://odibets.com/web/virtual/matches',
    'https://odibets.com/web/virtual/livescore '
]

least_v = 2.4
fallback_outcome = 9.0
min_stake, max_stake = 10, 20000
home_odds, away_odds = 'Home', 'Away'


def req_login():
    proceed_opt, cancel_opt = 'Proceed', 'Cancel'
    current_opt = proceed_opt
    try:
        current_opt = confirm(text='Login to your Odibet account, then click Procced',  buttons=[
            proceed_opt, cancel_opt])
    except:
        print('Failed to display Confirmation box.')
    if current_opt != proceed_opt:
        exit("Proceed option wasn't selected. Stopping.")


def assert_logged_in():
    try:
        driver.find_element_by_class_name("mybal")
    except:
        try:
            driver.find_element_by_css_selector(
                'a.l-account-links:nth-child(1)')
        except:
            driver.close()
            exit('Not logged in. Stopping')


def open_leagues():
    driver.get("https://odibets.com/league")


def open_market():
    del driver.requests
    driver.find_element_by_css_selector(
        '.l-leagues-tabs > li:nth-child(1) > button:nth-child(1)').click()


def wait_for_next_match():
    try:
        driver.wait_for_request(
            'https://odibets.com/web/virtual/matches', timeout=120)
    except:
        driver.get("https://odibets.com/league")
        print('Retrying...')
        wait_for_next_match()


def select_home_away_market():
    WebDriverWait(driver, 120).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'span.market > select:nth-child(1)')))
    select = Select(driver.find_element_by_css_selector(
        'span.market > select:nth-child(1)'))
    del driver.requests
    select.select_by_value('')


def get_matches():
    res = driver.wait_for_request(
        'https://odibets.com/web/virtual/matches', timeout=120).response
    if res.status_code != 200:
        driver.close()
        exit('Odibet response failed')
    return json.loads(res.body.decode('utf-8'))['matches']


def get_match_indices(matches, least_v):
    match_idx = []
    for i in range(len(matches)):
        o = matches[i]['outcomes']
        if float(o[0]['odd_value']) > least_v and float(o[2]['odd_value']) > least_v:
            match_idx.append(i)
    return match_idx


def get_odd_factors(matches, match_idx):
    odd_factors = []
    for i in match_idx:
        odd_factors.append([float(matches[i]['outcomes'][0]['odd_value']), float(matches[i]['outcomes'][2]['odd_value'])])
    return odd_factors


def calc_stake(outcome, odd_factors):
    stake = 0
    n = len(odd_factors)
    for odd_factor in odd_factors:
        stake = stake + (outcome / (odd_factor[0] + odd_factor[1] - 2)) / n
    stake = max(min_stake, min(max_stake, round(stake)))
    return stake


def calc_win_outcome(odd_factor, stake):
    return outcome + round(stake * odd_factor, 2)


def select_match_bet(bet_opt, match_idx):
    row = match_idx + 1
    col = 0 if bet_opt == home_odds else 2
    WebDriverWait(driver, 120).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, f'div.event:nth-child({row}) > div:nth-child(2) > div:nth-child(1) >  button')))
    try:
        driver.find_elements_by_css_selector(
            f'div.event:nth-child({row}) > div:nth-child(2) > div:nth-child(1) >  button')[col].click()
    except:
        driver.execute_script("arguments[0].scrollIntoView(false);", driver.find_element_by_xpath(
            f'div.event:nth-child({row})'))
        sleep(1)


def open_bet_slip():
    WebDriverWait(driver, 120).until(
        EC.presence_of_element_located((By.ID, 'betslip-bottom-betslip')))
    driver.find_element_by_id('betslip-bottom-betslip').click()


def fill_stake(stake):
    WebDriverWait(driver, 120).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '.stk-input > input:nth-child(1)')))
    driver.find_element_by_css_selector(
        '.stk-input > input:nth-child(1)').clear()
    driver.find_element_by_css_selector(
        '.stk-input > input:nth-child(1)').send_keys(str(stake))


def place_bet():
    driver.find_element_by_css_selector('.ct > button:nth-child(1)').click()


def close_bet_slip():
    driver.find_element_by_xpath(
        '/html/body/div/div[1]/div[3]/div[3]/div/div[1]/div[5]/i').click()


def get_results(match_idx):
    WebDriverWait(driver, 120).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '.l-leagues-tabs > li:nth-child(2) > button:nth-child(1)')))
    del driver.requests
    driver.find_element_by_css_selector(
        '.l-leagues-tabs > li:nth-child(2) > button:nth-child(1)').click()
    res = driver.wait_for_request(
        'https://odibets.com/web/virtual/matches', timeout=120).response
    if res.status_code != 200:
        exit('Odibet response failed')
    json_res = json.loads(res.body.decode('utf-8'))
    # apparently matches are reversed here
    results = []
    for i in match_idx:
        results.append(json_res['results'][0]['matches']
                       [-(i + 1)]['result'].split(':'))
    return results


def calc_profit(results, odd_factors, stake):
    profit = 0
    for i in range(len(results)):
        r1, r2 = int(results[i][0]), int(results[i][1])
        odds = odd_factors[i]
        profit = profit - \
            stake if r1 == r2 else (odds[0] - 2) * \
            stake if r1 > r2 else (odds[1] - 2) * stake
    return profit


def single_pass(outcome, profit):
    open_market()
    wait_for_next_match()
    select_home_away_market()

    matches = get_matches()
    match_idx = get_match_indices(matches, least_v)
    odd_factors = get_odd_factors(matches, match_idx)
    stake = calc_stake(outcome, odd_factors)
    win_outcome = 0
    start_time = parsedate(matches[match_idx]['start_time'])
    end_time = parsedate(matches[match_idx]['end_time'])

    matched_idx = []

    for m in range(len(match_idx)):
        if start_time > datetime.now() + timedelta(seconds=20):
            win_outcome = win_outcome + calc_win_outcome(odd_factors[m], stake)
            print(f'Stake = {stake}')
            print(f'Odds = {odd_factors}')
            print(f'Winning outcome = {win_outcome}')

            select_match_bet(home_odds, match_idx[m])
            open_bet_slip()
            fill_stake(stake)
            # place_bet()
            sleep(3)
            close_bet_slip()
            matched_idx.append(match_idx[m])

    pause.until(end_time)

    if len(matched_idx) != 0:
        results = get_results(matched_idx)
        profit = calc_profit(results, odd_factors, stake)
        lost = profit < 0
        outcome = win_outcome / len(results) if lost else fallback_outcome

        print(f'Results = {results}')
        print(
            f'Lost {-profit}' if lost else f'Gained {profit}')

        return outcome, profit
    else:
        return single_pass(outcome, profit)


driver.get("https://odibets.com/how-to-play")

req_login()
sleep(1)
open_leagues()
assert_logged_in()

outcome = fallback_outcome
profit = 0.0

for i in range(100):
    outcome, profit = single_pass(outcome, profit)
    print(f'Total Profit = {profit}')
    print()

driver.close()
