"""Chrome 드라이버 생성."""
from selenium import webdriver


def make_driver(headless=False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")
    return webdriver.Chrome(options=options)
