from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
import requests
import functools
import csv
import re
import json
import os

from time import sleep
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC



class resultsDriver:
    """
    A class using Selenium to traverse the list of match results on www.rib.gg/results.
    For each match, a jsonParser object will be created to pull information about the match
    and parse that information. Then that information is written into the csv in this class.

    Attributes
    ----------
    fileName : str
        the name of the csv file the match data will be written to
    numSeries : str
        the number of series that will be recorded
    fileExists : bool
        determines if the provided file name already exists

    Methods
    -------
    get_series(startNum=1)
        Creates a Selenium driver to traverse each series in the results page. Then process_series
        is called to extract information from each match in the series.
    process_series(series)
        Takes a BeautifulSoup object corresponding to a series row from the results page and
        extracts a link to each match in the series. A jsonParser object is then created to get 
        information about the match. This information is then written into the csv.
    """

    def __init__(self, fileName='pro_val_matches.csv', numSeries=10000):
        """
        Parameters
        ----------
        fileName : str
            The name of the csv file to be written to
        numSeries : int
            The number of series to be recorded
        """
        self.fileName = fileName
        if (self.fileName[-4:] != '.csv'):
            self.fileName += '.csv'
        self.numMatches = numSeries

        # check if the file exists
        self.fileExists = os.path.isfile(fileName)

    def get_series(self, startNum=1):
        """ Creates a Selenium driver to traverse each series in the results page. Then process_series
        is called to extract information from each match in the series.

        If the argument `startNum` is not provided, the default value is 1, corresponding to the first
        series on the results page.

        Parameters
        ----------
        startNum : int
            The index of the series to start recording at
        """
        url = 'https://www.rib.gg/results'
    
        options = webdriver.ChromeOptions()

        #options.add_argument('--headless')
        # macOS Chrome location
        #options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

        driver = webdriver.Chrome(options=options)
        driver.get(url)

        element = WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.XPATH, "//div[@class='MuiBox-root css-1iqrfdr']/a[3]")))
        driver.execute_script("arguments[0].scrollIntoView(true);", element)

        # getting start position in webpage, this puts the correct series link at the top of the page
        # scrolling 20 series at a time to speed up scrolling
        for i in range((startNum-1)//20):
            element = WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.XPATH, "//div[@class='MuiBox-root css-1iqrfdr']/a[23]")))
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            sleep(1)
        # scrolling 1 series at a time to get to exact start location
        for i in range((startNum-1)%20):
            element = driver.find_element(By.XPATH, "//div[@class='MuiBox-root css-1iqrfdr']/a[4]")
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            sleep(1)

        countSeries = startNum-1
        while (countSeries <= self.numSeries):
            results_page = driver.page_source
            result_soup = BeautifulSoup(results_page, features='html.parser') 
            series_list = result_soup.find_all('div', class_='MuiBox-root css-7erhtc')[0:20]
            for series in (series_list):
                countSeries += 1
                print(countSeries)
                self.process_series(series)

            element = driver.find_element(By.XPATH, "//div[@class='MuiBox-root css-1iqrfdr']/a[23]")
            sleep(1)
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            sleep(1)


    def process_series(self, series):
        """Takes a BeautifulSoup object corresponding to a series row from the results page and
        extracts a link to each match in the series. A jsonParser object is then created to get 
        information about the match. This information is then written into the csv.

        Parameters
        ----------
        series : BeautifulSoup object
            A BeautifulSoup object corresponding to a row from the results page
        """
        map_list = series.find_all('a', class_='MuiTypography-root MuiTypography-inherit MuiLink-root MuiLink-underlineAlways css-qej84z')
        map_links = list(map(lambda x: x['href'], map_list))
        if (map_links):
            map_links.sort(key=lambda x: x[x.rfind('=')+1:])
        
        matches = []
        for tail in map_links:
            link = 'https://www.rib.gg' + tail
            
            print(link)
            if (not self.fileExists): # check if header should be added to csv file
                parser = jsonParser(link, addHeader=True)
                self.fileExists = True
            else:
                parser = jsonParser(link)
            matches.append(parser.csv_rows())
        with open(self.fileName, 'a') as file:
            writer = csv.writer(file)
            for match in matches:
                for row in match:
                    writer.writerow(row)
                    file.flush()

            

class jsonParser:
    """
    A class that takes a url from a specific match and returns a dictionary containing
    information about the match.

    Attributes
    ----------
    form : dict
        a dictionary containing all information about the match
    match_id : int
        the rib.gg match id of the match
    addHeader : bool
        a boolean that will determine if a header row should be written to the csv

    Methods
    -------
    get_match_info()
        Returns a dictionary containing information about the match.
    player_stats_data()
        Returns an array containing information about each player for each round of the match.
    get_rounds()
        Returns an array containing information about each round of the match. Calls
        player_stats_data in order to get player information about each round.
    get_ign_dict()
        Returns a dictionary with players' id numbers as keys and their in game names as values.
    get_weapon_dict()
        Returns a dictionary with weapons' id numbers as keys and the weapon names as values.
    get_agent_dict()
        Returns a dictionary with agents' id numbers as keys and their agent names as values.
    get_region_dict()
        Returns a dictionary with the regions' id numbers as keys and the region names as values.
    csv_rows()
        Returns an array with elements corresponding to rows containing information about the match
        and its rounds to be written into a csv.
    """
    # make an http request to pull data from rib.gg upon init
    def __init__(self, url, addHeader=False):
        """Creates a get request to the given url and stores the data in attributes.
        The get request will be attempted 10 times, if this is not successful, the 
        match will be skipped.

        Parameters
        ----------
        url : string
            The url of the match.
        addHeader : bool
            A boolean that will determine if a header row should be written to the csv.
        """
        response = None
        count = 0
        # attempt 10 get requests before quitting
        while (not response and count < 11):
            try:
                count += 1
                if (count > 1):
                    print(f'Get request attempt {count}')
                response = requests.get(url)
            except requests.Timeout:
                print('Timed out, attempting another get request.')

        # throw away match data if get request was faulty
        if (response.status_code == 500):
            print('Tossing match, failed get request.')
            return

        # pull page html content and get json with match data
        source = response.content
        soup = BeautifulSoup(source, features='html.parser')
        script = soup.find('script', {'id':'__NEXT_DATA__'})
        if (script):
            data =  script.string
        else: # quit if match data json is not present
            print('Tossing match, no json available.')
            return
        
        self.form = json.loads(data)['props']['pageProps']
        self.match_id = self.form['matchId']
        self.addHeader = addHeader

    def get_match_info(self):
        """Returns a dictionary containing information about the match.
        """
        index = None
        # find the correct index of current match
        for num, match in enumerate(self.form['series']['matches']):
            if (match['id'] == self.match_id):
                index = num
                break

        regionDict = self.get_region_dict()
        
        matchInfo = {
            # info of series
            'parentEvent': self.form['series']['parentEventName'],
            'eventName': self.form['series']['eventName'],
            'eventTime': self.form['series']['startDate'],
            'eventRegion': regionDict[self.form['series']['eventRegionId']],
            'bestOf': self.form['series']['bestOf'],
            'stage': self.form['series']['stage'],
            'bracket': self.form['series']['bracket'],
            'team1': self.form['series']['team1']['name'],
            'team2': self.form['series']['team2']['name'],
            'team1SeriesScore' : self.form['series']['team1Score'],
            'team2SeriesScore' : self.form['series']['team2Score'],

            #info of match
            'matchId': self.match_id,
            'mapName': self.form['series']['matches'][index]['map']['name'],
            'gameStartTime': self.form['series']['matches'][index]['startDate'],
            'seriesMatchNumber': self.form['series']['matches'][index]['seriesMatchNumber'],
            'patchId': self.form['series']['matches'][index]['patchId'],
            'seriesWinningTeamNumber': self.form['series']['matches'][index]['winningTeamNumber'],
            'team1MatchScore': self.form['series']['matches'][index]['team1Score'],
            'team2MatchScore': self.form['series']['matches'][index]['team2Score'],
            'seriesWinCondition': self.form['series']['matches'][index]['winCondition'],
        }

        return matchInfo


    def player_stats_data(self):
        """Returns an array containing information about each player for each round of the match.
        Each element of the array is a dictionary containing how much money the player spent, what
        weapon they have at the start of the round, their kills, assists, plant information, and
        other information.
        """
        playerStats = self.form['series']['playerStats']
        playerStats = list(filter(lambda x: x['matchId']==self.match_id, playerStats))
        economy = self.form['matchDetails']['economies']
        
        # these dictionaries allow us to replace playerIds, agentIds, and weaponIds with names
        ignDict = self.get_ign_dict()
        numPlayers = max(len(ignDict),1)
        agentDict = self.get_agent_dict()
        weaponDict = self.get_weapon_dict()

        team1Players = []
        team2Players = []

        # grouping player information by round
        for i in range(0, len(playerStats), numPlayers):
            econWindow = economy[i:i+numPlayers]
            team1Round = []
            team2Round = []
            # putting together player stats with player economy data into one dictionary
            for j in range(i, i+numPlayers):
                for player in econWindow:
                    if (playerStats[j]['playerId'] == player['playerId'] and playerStats[j]['roundNumber'] == player['roundNumber']):
                        playerEcon = econWindow.pop(econWindow.index(player))
                        playerEcon.update(playerStats[j])
                        playerStats[j] = playerEcon
                        
                        # change id numbers into actual names
                        playerStats[j]['playerIgn'] = ignDict[playerStats[j]['playerId']]
                        playerStats[j]['agent'] = agentDict[playerStats[j]['agentId']]
                        if (playerStats[j]['weaponId']):
                            playerStats[j]['weaponName'] = weaponDict[playerStats[j]['weaponId']]

                        # get rid of unnecessary player information
                        del playerStats[j]['playerId']
                        del playerStats[j]['agentId']
                        del playerStats[j]['weaponId']

                        if (playerStats[j]['teamNumber'] == 1):
                            team1Round.append(playerStats[j].copy())
                        else:
                            team2Round.append(playerStats[j].copy())
                        break
            team1Players.append(team1Round.copy())
            team2Players.append(team2Round.copy())

        return([team1Players, team2Players])


    def get_rounds(self):
        """Returns an array containing information about each round of the match. Calls
        player_stats_data in order to get player information about each round.
        """
        index = None
        for num, match in enumerate(self.form['series']['matches']):
            if (match['id'] == self.match_id):
                index = num
                break

        rounds = self.form['series']['matches'][index]['rounds']
        playerData = self.player_stats_data()

        for num, round in enumerate(rounds):
            if (playerData[0][num]):
                round['team1Players'] = playerData[0][num]
            else: 
                round['team1Players'] = None
 
            if (playerData[1][num]):
                round['team2Players'] = playerData[1][num]
            else:
                round['team2Players'] = None

        return rounds


    def get_ign_dict(self):
        """Returns a dictionary with players' id numbers as keys and their in game names as values.
        """
        player_dict = {}
        index = None

        for num, match in enumerate(self.form['series']['matches']):
            if (match['id'] == self.match_id):
                index = num
                break

        for player in self.form['series']['matches'][index]['players']:
            player_dict[player['player']['id']] = player['player']['ign']
        return player_dict


    def get_weapon_dict(self):
        """Returns a dictionary with weapons' id numbers as keys and the weapon names as values.
        """
        weapon_dict = {}
        for weapon in self.form['content']['weapons']:
            weapon_dict[weapon['id']] = weapon['name']
        return weapon_dict


    def get_agent_dict(self):
        """Returns a dictionary with agents' id numbers as keys and their agent names as values.
        """
        agent_dict = {}
        for agent in self.form['content']['agents']:
            agent_dict[agent['id']] = agent['name']
        return agent_dict
    

    def get_region_dict(self):
        """Returns a dictionary with the regions' id numbers as keys and the region names as values.
        """
        regionDict = {}
        for region in self.form['content']['regions']:
            regionDict[region['id']] = region['name']
        return regionDict
    

    def csv_rows(self):
        """Returns an array with elements corresponding to rows containing information about the match
        and its rounds to be written into a csv.
        """
        if (not self.form or self.form.get('statusCode') == 500):
            print('Tossing match.')
            return []

        matchData = self.get_match_info()
        rounds = self.get_rounds()

        output = []

        if (not rounds):
            output.append(list(matchData.values()))
        else:
            # writes a header first before adding values
            if (self.addHeader):
                output.append(list(matchData.keys()) + list(rounds[0].keys()))
            for round in rounds:
                output.append(list(matchData.values()) + list(round.values()))

        return output

driver = resultsDriver('pro_val_matches.csv')
driver.get_series()
