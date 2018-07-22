#!/usr/bin/env python3
import os
import re
import sys
import time
import datetime
import getopt

from selenium import webdriver

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import traceback
from selenium.webdriver.firefox.options import Options
from enum import Enum

from pathlib import Path
from random import shuffle


class Status(Enum):
    INIT=61
    LOGIN_FAILED=62
    LOGGED_IN=62
    SEARCHING=63
    ACCOUNT_ACTIVATED=0
    ACCOUNT_ALREADY_ACTIVATED=65
    TIMEOUT=64

class CrunchyrollGuestPassFinder:

    endOfGuestPassThreadPage = "http://www.crunchyroll.com/forumtopic-803801/the-official-guest-pass-thread-read-opening-post-first?pg=last"
    redeemGuestPassPage = "http://www.crunchyroll.com/coupon_redeem?code="
    failedGuestPassRedeemPage="http://www.crunchyroll.com/coupon_redeem"
    loginPage = "https://www.crunchyroll.com/login"
    homePage = "http://www.crunchyroll.com"
    GUEST_PASS_PATTERN = "[A-Z0-9]{11}"
    timeout = 10
    invalidResponse = "Coupon code not found."

    HEADLESS = True
    CONFIG_DIR=str(Path.home())+"/.config/taapcrunchyroll-bot/"
  
    KILL_TIME = 43200 # after x seconds the program will quit with exit code 64
    DELAY = 10 # the delay between refreshing the guest pass page
    
    status=Status.INIT
    
    def __init__(self,username,password):
        self.output("starting bot")
        firefox_profile = webdriver.FirefoxProfile()
        firefox_profile.set_preference('permissions.default.image', 2)
        firefox_profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', 'false')
        options = Options()
        if self.isHeadless():
            options.add_argument("--headless")
        self.driver = webdriver.Firefox(log_path="/dev/null", firefox_options=options,firefox_profile=firefox_profile)
        self.driver.implicitly_wait(self.timeout)
        self.driver.set_page_load_timeout(self.timeout)
        self.startTime = time.time()
        self.username = username
        self.password = password
        self.output("inital status",self.status)
        
    def isHeadless(self):
        return self.HEADLESS
    def isTimeout(self):
        if time.time() - self.startTime >= self.KILL_TIME:
            return True
        else:
            return False
    def login(self):
        self.output("attemting to login to "+self.username)
        self.driver.get(self.loginPage)
        self.driver.find_element_by_id("login_form_name").send_keys(self.username)
        self.driver.find_element_by_id("login_form_password").send_keys(self.password)
        self.driver.find_element_by_class_name("type-primary").click()

        self.output("logged in")
        self.output(self.driver.current_url)
        if self.driver.current_url==self.loginPage:
            self.saveScreenshot("logged-in-failed.png")
            self.status=Status.LOGIN_FAILED
            return False
        
        self.status=Status.LOGGED_IN
        return True
        
        
    def waitForElementToLoad(self,id):
        element_present = EC.presence_of_element_located((By.ID, id))
        WebDriverWait(self.driver, self.timeout).until(element_present)
    def waitForElementToLoadByClass(self,clazz):
        element_present = EC.presence_of_element_located((By.CLASS_NAME, clazz))
        WebDriverWait(self.driver, self.timeout).until(element_present)
        
    def isAccountNonPremium(self,init=False):
        try:
            self.waitForElementToLoadByClass("premium")
            return True
        except TimeoutException:
            self.output("Could not find indicator of non-premium account; exiting")
            if init:
                self.status=Status.ACCOUNT_ALREADY_ACTIVATED
            self.saveScreenshot("alreadyPremium")
            return False
            
    def activeCode(self,code):
        try:
            self.driver.get(self.redeemGuestPassPage+code)

            self.output("currentURL:",self.driver.current_url)
            self.waitForElementToLoad("couponcode_redeem_form")
            self.driver.find_element_by_id("couponcode_redeem_form").submit()
            

            if self.isAccountNonPremium():
                self.output("False positive. account is still non premium")
            else:                        
                self.postTakenGuestPass(code)
                self.output("found guest pass %s; exiting" % str(code))
                self.status=Status.ACCOUNT_ACTIVATED
                return code
            self.output("URL after submit:",self.driver.current_url)
        except TimeoutException:
            traceback.print_exc(2)
            pass
        return None
    def startFreeAccess(self):
        count = -1
        usedCodes = []
        timeOfLastCheck = 0
        self.status=Status.SEARCHING
        self.output("searching for guest passes")
        if not self.isAccountNonPremium(True):
            return None
        while True:
            count += 1
            try:
                guestCodes = self.findGuestPass()

                unusedGuestCodes = [x for x in guestCodes if x not in usedCodes]

                if len(unusedGuestCodes) > 0:
                    self.output("Trial ",count,": found ",len(unusedGuestCodes)," codes: ",unusedGuestCodes,"; ", len(usedCodes), " others have been used: ",usedCodes)
                    timeOfLastCheck = time.time()
                    shuffle(unusedGuestCodes)
                elif time.time()-timeOfLastCheck > 600:
                    self.output("Trial ",count, "url",self.driver.current_url)
                    sys.stdout.flush()
                    timeOfLastCheck = time.time()
                if self.isTimeout():
                    self.status=Status.TIMEOUT
                    return None
                    
                for code in unusedGuestCodes:
                    if self.activeCode(code):
                        return code
                    usedCodes.append(code)

                time.sleep(self.DELAY)
                if(len(unusedGuestCodes)): #only check if we just attempted
                    if not self.isAccountNonPremium():
                        self.output("currentURL:", self.driver.current_url)
                        self.status=Status.ACCOUNT_ACTIVATED
                        return None
            except TimeoutException:
                pass
            except BrokenPipeError:
                traceback.print_exc(2)


    def postTakenGuestPass(self,guestPass):
        try:
            self.output("attempting to post that guest pass was taken")
            self.driver.get(self.endOfGuestPassThreadPage)
            self.driver.find_element_by_id("newforumpost").send_keys(guestPass+" has been taken.\nThanks")
            self.saveScreenshot("posted_guest_pass")
            self.driver.find_element_by_name("post_btn").click()
        except TimeoutException:
            self.output("failed to post guest pass");
                
    def findGuestPass(self):
        guestCodes=[]
        inValidGuestCodes=[]
        try:
            self.driver.get(self.endOfGuestPassThreadPage)
            classes=self.driver.find_elements_by_class_name("showforumtopic-message-contents-text")
            for i in range(len(classes)):

                matches = re.findall(self.GUEST_PASS_PATTERN,classes[i].text,re.M)

                if matches:
                    for n in range(len(matches)):
                        if matches[n] not in guestCodes:
            
                            guestCodes.append(matches[n])
                        elif matches[n] not in inValidGuestCodes:
                            inValidGuestCodes.append(matches[n])
        except TimeoutException:
            traceback.print_exc(2)
        for i in range(len(inValidGuestCodes)):
            guestCodes.remove(inValidGuestCodes[i])

        return guestCodes

    def saveScreenshot(self,fileName="screenshot.png"):
        fileName+=".png"
        self.output("saving screen shot to ",fileName)
        self.driver.save_screenshot(self.CONFIG_DIR+fileName)
        pass

    def output(self,*message):

        time=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")+":"
        formattedMessage=message[0]
        for i in range(1,len(message)):
            formattedMessage+=str(message[i])
        print(time,formattedMessage, flush=True)

    def getStatus(self):
        return self.status.value
    def close(self):
        self.output("exiting")
        if self.isHeadless():
            self.driver.quit()


if __name__ == "__main__":

    shortargs="gk:d:"
    longargs=["graphical","kill-time=","config-dir=","delay="]
    optlist, args = getopt.getopt(sys.argv[1:],shortargs,longargs)
    for opt,value in optlist:
        if opt == "-g" or opt == "--graphical":
            CrunchyrollGuestPassFinder.HEADLESS = False
        elif opt == "-k" or opt == "--kill-time":
            CrunchyrollGuestPassFinder.KILL_TIME = int(value)
        elif opt == "-d" or opt == "-delay":
            CrunchyrollGuestPassFinder.DELAY = int(value)
        elif opt == "--config-dir=":
            CrunchyrollGuestPassFinder.CONFIG_DIR = value
            
        else:
            raise ValueError("Unkown argument: ",opt)
            
    if len(args) <= 2:
        username = input("Username:") if len(args) == 0 else args[0]
        password = input("Password:") if len(args) <= 1 else args[1]
    else:
        raise ValueError("Too many arguments")
        
    if not os.path.exists(CrunchyrollGuestPassFinder.CONFIG_DIR):
        print("WARNING the dir specified does not exists:",CrunchyrollGuestPassFinder.CONFIG_DIR)
    crunchyrollGuestPassFinder = CrunchyrollGuestPassFinder(username, password)
    if crunchyrollGuestPassFinder.login():
        crunchyrollGuestPassFinder.startFreeAccess()
    crunchyrollGuestPassFinder.close()
    print("status = %d" % crunchyrollGuestPassFinder.getStatus())
    exit(crunchyrollGuestPassFinder.getStatus())
