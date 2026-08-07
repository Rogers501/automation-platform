"""jmsco 页面对象层 (Page Object Model).

- BasePage: 封装 WebClient 通用操作, 所有页面对象继承它 (rule 4/8).
- LoginPage: 登录页选择器与操作.
- SlidePuzzleCaptcha: 滑块验证码处理器 (人工滑动).
"""

from pages.base_page import BasePage
from pages.captcha_page import SlidePuzzleCaptcha
from pages.login_page import LoginPage

__all__ = ["BasePage", "LoginPage", "SlidePuzzleCaptcha"]
