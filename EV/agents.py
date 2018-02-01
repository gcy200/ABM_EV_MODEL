#   agents.py

import matplotlib.pyplot as plt
import numpy as np
import random
import math
from mesa import Agent, Model
from mesa.time import RandomActivation
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector
from scipy.spatial import distance


# Create charging pole agents
class Charge_pole(Agent):
    def __init__(self, unique_id, pos, model):
        super().__init__(pos, model)
        self.initial_free_poles = 2
        self.free_poles = 2 
        self.usage = []
        

    def step(self):
        self.usage.append( 1- (self.free_poles / self.initial_free_poles))
        self.avg_usage = np.mean(self.usage[-200:])

# Create the Electric Vehicles agents
class EV_Agent(Agent):
    """ An agent with fixed initial battery."""

    def __init__(self, unique_id, model, vision, home_pos, work_pos, initial_bravery, battery_size = 75):
        super().__init__(unique_id, model)
        self.unique_id = unique_id
        self.vision = vision                                        # taken from a slider input
        self.max_battery = np.random.randint(70,80)                 # maximum battery size, differs for different cars is between 70 and 80 kwh (all tesla)
        self.battery = np.random.randint(50,self.max_battery)       # starting battery 
        self.usual_charge_time = np.random.normal(25,10) 			# the time period for how long it usually charges
        self.charge_speed = 3                                       # the battery increase for every timestep at a charge station
        self.time_charging = 0
        self.state = np.random.choice(["working", "shopping", "at_home", "traveling"])	#inital state
        self.time_in_state = np.random.randint(0,30)	#initial value to make sure not everyone moves at the same time
        self.how_long_at_work = np.random.normal(25, 3)  #initial value for time to stay at work
        self.how_long_shopping = np.random.normal(5, 3)
        self.how_long_at_home = np.random.normal(30, 5) #if at home, ususally stays for 30 timesteps
        self.minimum_battery_to_look_for_cp = abs(np.random.normal(30, 10))
        self.critical_battery_limit = abs(np.random.normal(5,1))
        self.age = 0

        # test case
        if battery_size < 70:
            self.max_battery = np.random.randint(0.9 * battery_size,1.1 * battery_size)
            self.battery = np.random.randint(0.75*battery_size, self.max_battery)
            self.minimum_battery_to_look_for_cp = abs(np.random.normal(0.5*battery_size, 0.1*battery_size))
            
        
        
        self.current_strategy = 0
        self.pole_count = 0                                                # counts the amount of charging_pole encounters (to calculate the 'age' of memories)
        self.strategies = [[1,1,1,1,1,1,1,1,1,1],[1,1,1,1,1,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0]] # different strategies used, which memories count in each strategy
        self.initMemory() 
        #self.possible_steps = []
        self.offLimits = []
        self.prev_target = ""
        self.prev_target_pos = []
        self.cpf = [0.25,0.5,0.75,1.0] 
        self.attempts_success = 0
        self.attempts_failed = 0
        # the amount of tiles it will explore away from the middle between home and work is normally distributed
        # this will be lower the more poles found, and is exponentially distributed.
        self.initial_bravery = abs(round(np.random.normal(initial_bravery, 5)))

        self.time_in_state = 0
        self.home_pos = home_pos            # Agent lives here
        self.pos = home_pos
        self.work_pos = work_pos            # Agent works here
        self.chooseCenterPos()
        self.shopping_pos = (0, 0)          # Will be set later
        self.target = np.random.choice(["work", "home", "shop"])             # has one of the targets first
        if self.target == "home":
            self.target_pos = home_pos
        elif self.target == "shop":
            self.newRandomPos()
        else:
            self.target_pos = work_pos
        self.state = "traveling"
        self.setDirection()

    # can randomly move in the neighbourhood with radius = vision
    def move(self):
        self.age += 1
        #if self.unique_id == 0:
            #print("position:",self.pos,"target:",self.target,"target position:",self.target_pos,"state:",self.state,"home:", self.home_pos, "work:",self.work_pos,"center:",self.center_pos,"direction:",self.direction)
        self.checkTargets()
        if self.state == "traveling":  # if not waiting/charging:
            self.getNeighbourhood()                                             # - find possible moves and register charging poles within vision
            self.chooseNextStep()                                               # - choose next steps based on target and possible moves
            self.moveEV()                                                       # move and use battery

    # registers possible moves and charging pole positions    
    def getNeighbourhood(self):
        #self.possible_steps = self.model.grid.get_neighborhood(self.pos,radius = 1,moore=True,include_center=True) # possible moves
        self.polesInSight = self.checkForPoles()  # returns positions of all poles within vision

        done = False
        neighbors = []    # array of neighbors, saved to prevent updating the memory of the same pole many times in a row, because it is close
        # for each pole in vision, if not just updated, check for free spaces and update memory
        for point in self.polesInSight:
            if self.inLastPoints(point) == False:
                neighbors.append(point)
                if self.checkIfFree(point)>0:
                    self.updateMemory(1,point)
                    # if the pole has space and the battery is very low or no other pole was chosen yet, it sets the pole as target (to give the strategies a chance I don't always grab the closest pole)
                    if (self.battery < self.critical_battery_limit and done == False) or (self.battery < self.minimum_battery_to_look_for_cp and self.target != "charge_pole"):
                        if self.target != "charge_pole" and self.target != "searching": 
                            self.prev_target = self.target           # store target and position to continue to after charging
                            self.prev_target_pos = self.target_pos
                        self.target_pos = point
                        self.setDirection()
                        self.target = "charge_pole"
                        done = True
                else:
                    # if the pole is full, store this information to memory so when looking for a pole it won't visit the 3 (at this point) last full poles it passed by
                    self.updateMemory(-1,point)
                    if self.battery < 100:
                        self.offLimits = [point]
        self.neighborMemory(neighbors)

    # adds all new neighboring poles to memory, replacing older memories
    def neighborMemory(self,neighbors):  
        self.memory["neighborPoles"] = [neighbors], self.memory["neighborPoles"][:-1]

    # checks for poles within self.vision and returns the positions
    def checkForPoles(self):  
        poles = []
        neig = self.model.grid.get_neighbors(self.pos,radius = self.vision,moore=True,include_center=True)
        for agent in neig:
            if type(agent) == Charge_pole:
                poles.append(agent.pos)
        return poles

    # returns the free sockets of a pole at a given position
    def checkIfFree(self,pos):
        for agent in self.model.grid.get_cell_list_contents(pos):
            if type(agent) == Charge_pole:
                return agent.free_poles

    # registers that the car starts charging and a space at the pole is taken
    def takePlace(self):
        for agent in self.model.grid.get_cell_list_contents((self.pos[0],self.pos[1])):
            if type(agent) == Charge_pole:
                agent.free_poles = agent.free_poles - 1

    # registers that charging is complete and a space at the pole is freed
    def freePlace(self):
        for agent in self.model.grid.get_cell_list_contents((self.pos[0],self.pos[1])):
            if type(agent) == Charge_pole:
                agent.free_poles = agent.free_poles + 1

    # checks whether given position is in neighborMemory
    # to prevent from updating the same pole memory every step
    def inLastPoints(self,pos):
        for timepoint in self.memory["neighborPoles"]:
            for coordinate in timepoint:
                if coordinate == pos:
                    return True
        return False
    
    # charges and checks if conditions for charging complete are met
    def charge(self):
        self.time_charging = self.time_charging + 1
        if self.time_charging < self.usual_charge_time or self.battery < self.max_battery:  #self.time_charging < self.usual_charge_time or
            if self.battery < self.max_battery:
                self.battery += self.charge_speed
                if self.battery > self.max_battery:
                    self.battery = self.max_battery
        # if battery is done charging and minimum charging time is over, stop charging
        else: 
            # resets values, goes back to previous targets and frees socket space
            self.target = self.prev_target
            self.target_pos = self.prev_target_pos
            self.state = "traveling"
            self.setDirection()
            self.time_charging = 0
            self.current_strategy = 0
            self.offLimits = []
            self.freePlace()

    # checks whether EV needs to look for charger and whether targets are reached
    def checkTargets(self):

        if self.battery < self.minimum_battery_to_look_for_cp and self.target != "charge_pole" and self.target != "searching":
            self.chooseTargetPole()

        if self.target_pos[0] == self.pos[0] and self.target_pos[1] == self.pos[1]:
            if self.unique_id == 0:
                ...
                #print("target reached!")
            # Target: work -> shopping, shopping -> home, home -> work, searching -> searching (new target position), charge_pole -> ____ -> prev_target
            if self.target == "work":
                if self.state == "working":
                    if self.time_in_state < self.how_long_at_work:
                        self.time_in_state += 1
                    else:
                        self.time_in_state = 0
                        self.target = "shop"
                        self.how_long_shopping = np.random.normal(5, 3)  # if at shopping center, stays around 5 timesteps
                        self.newRandomPos()  # self.target_pos is selected
                else:
                    self.state = "working"
            elif self.target == "shop":
                if self.state == "shopping":
                    if self.time_in_state < self.how_long_shopping:
                        self.time_in_state += 1
                    else:
                        self.time_in_state = 0
                        self.target = "home"
                        self.how_long_at_home = np.random.normal(30, 5) #if at home, ususally stays for 30 timesteps
                        self.target_pos = self.home_pos[:]
                        self.setDirection()
                else:
                    self.state = "shopping"
            elif self.target == "searching":
                self.state = "searching"
                self.chooseTargetPole()
            elif self.target == "charge_pole":
                self.state = "charging"
                if self.time_charging == 0:
                    if self.checkIfFree((self.pos[0],self.pos[1])) > 0:
                        self.takePlace()
                        self.charge()
                        self.attempts_success+=1
                    else:
                        self.offLimits = self.pos
                        self.chooseTargetPole()
                        self.attempts_failed+=1
                else:
                    self.charge()
            else:
                if self.state == "at_home":
                    if self.time_in_state < self.how_long_at_home:
                        self.time_in_state += 1
                    else:
                        self.time_in_state = 0
                        self.target = "work"
                        self.how_long_at_work = np.random.normal(25, 3)  #if at work, ususally stays for 25 timesteps
                        self.target_pos = self.work_pos[:]
                        self.setDirection()
                else:
                    self.state = "at_home"
        else:
            self.state = "traveling"

    # not right yet, take another look
    def chooseCenterPos(self):
        if self.model.open:
            # for toroidal grid. chooses center position
            self.center_pos = []
            for i in range(2):
                # if difference between points larger than half of the grid, the center should lie 'outside', otherwise in the middle
                if abs(self.home_pos[i] - self.work_pos[i]) > 0.5 * self.model.grid.width: # assumes equal width and height
                    if self.home_pos[i] < self.work_pos[i]:
                        self.center_pos.append(self.home_pos[i] - int((self.home_pos[i] + (100-self.work_pos[i]))/2))
                    else:
                        self.center_pos.append(self.work_pos[i] - int((self.work_pos[i] + (100-self.home_pos[i]))/2))
                else: 
                    self.center_pos.append(int((self.home_pos[i] + self.work_pos[i]) / 2))
                if self.center_pos[i] < 0:
                    self.center_pos[i] += self.model.grid.width
                elif self.center_pos[i] >= self.model.grid.width:
                    self.center_pos[i] -= self.model.grid.width

        else:
            # Coordinates between home and work
            self.center_pos = ((self.home_pos[0]+self.work_pos[0])/2,(self.home_pos[1]+self.work_pos[1])/2)



    # chooses new random position around center_Pos
    def newRandomPos(self):
        polesInMemory = len(self.memory)- 5 # initial memory with strategies is 5, every pole added in memory is one extra

        
        if polesInMemory == 0:
            bravery = round(np.random.exponential(self.initial_bravery))
        else:
            bravery = round(np.random.exponential(self.initial_bravery/polesInMemory)) # exponential function to get random shopping position distance

        if self.model.open == False:
            newPos = [np.random.choice(np.max([self.center_pos[0] - bravery, 0]),np.min([self.center_pos[0] + bravery, self.model.grid.width - 1])),np.random.choice(np.max([self.center_pos[1] - bravery, 0]),np.min([self.center_pos[1] + bravery, self.model.grid.height - 1]))]
        else:
            newPos = [np.random.choice(np.arange(self.center_pos[0] - bravery,self.center_pos[0] + bravery + 1)), np.random.choice(np.arange(self.center_pos[1] - bravery,self.center_pos[1] + bravery + 1,1))]
            for i in range(2):
                if newPos[i] < 0:
                    newPos[i] = newPos[i] + self.model.grid.width
                elif newPos[i] >= self.model.grid.width:
                    newPos[i] = newPos[i] - self.model.grid.width
       
        self.target_pos = newPos
        self.setDirection()
                       
    def chooseNextStep(self):
        difference = []
        for i in range(2):
            difference.append(abs(self.target_pos[i]-self.pos[i]))
            if difference[i] > 0.5 * self.model.grid.width and self.model.open == True:
                difference[i] = self.model.grid.width - difference[i]
        new_position = [0,0]
        if difference[0] > difference[1]:
            new_position[0] = self.pos[0] + self.direction[0]
            if difference[1] == 0:
                new_position[1] = self.pos[1] 
            else: 
                if np.random.rand() < difference[1]/difference[0]:
                    new_position[1] = self.pos[1] + self.direction[1]
                else:
                    new_position[1] = self.pos[1] 
        elif difference[0] < difference[1]:
            new_position[1] = self.pos[1] + self.direction[1]
            if difference[0] == 0:
                new_position[0] = self.pos[0]
            else: 
                if np.random.rand() < difference[0]/difference[1]:
                    new_position[0] = self.pos[0] + self.direction[0]
                else:
                    new_position[0] = self.pos[0]
        else:
            new_position = [self.pos[0] + self.direction[0],self.pos[1] + self.direction[1]]
        
        for i in range(2):
            if new_position[i] == -1:
                new_position[i] = self.model.grid.width -1
            elif new_position[i] == self.model.grid.width:
                new_position[i] = 0

        self.new_position = new_position

    def setDirection(self):
        difference = (self.target_pos[0]-self.pos[0] ,self.target_pos[1]-self.pos[1])
        direction = [0,0]
        for i in range(2):
            if difference[i] > 0:
                if self.model.open == True and difference[i] > 0.5 * self.model.grid.width: # again assuming square grid
                    direction[i] = -1
                else:
                    direction[i] = 1
            elif difference[i] < 0:
                if self.model.open == True and difference[i] < - 0.5 * self.model.grid.width: # again assuming square grid
                    direction[i] = 1
                else: 
                    direction[i] = -1
        self.direction = direction
    
    # changes position an drains battery
    def moveEV(self):
        self.use_battery()
        self.model.grid.move_agent(self,self.new_position)
    
    # initiates memory dictionary and score dictionary
    def initMemory(self):
        self.memory = {}
        self.scores = {}
        for i in range(len(self.strategies)): # for each strategy create a (neutral) memory
            self.memory[i+1]=[[0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0]]
        self.memory["neighborPoles"] = [[0],[0],[0]]
        self.updateStrategies()

    # saves new memories
    def updateMemory(self,succes,pos):
        self.pole_count += 1
        if pos in self.memory:
            self.memory[pos] = [[succes]+self.memory[pos][0][:-1],[self.pole_count]+self.memory[pos][1][:-1]]
        else:
            self.memory[pos] = [[succes]+[0,0,0,0,0,0,0,0,0],[self.pole_count]+[0,0,0,0,0,0,0,0,0]]
        if self.current_strategy > 0 and pos[0] == self.target_pos[0] and pos[1] == self.target_pos[1]:
            self.memory[self.current_strategy] = [[succes]+self.memory[self.current_strategy][0][:-1],[self.pole_count]+self.memory[self.current_strategy][1][:-1]]
            self.updateStrategies()
        self.updateScores(pos)
    
    # updates cumulative probability function based on new memories for strategy    
    def updateStrategies(self):
        prev=0
        self.cpf = []
        for i in range(len(self.strategies)):
            next = (sum(self.ageCompensation(i+1)) + 10) # does this make sense? minimal -10, maximum 10. Make positive, nonzero number.
            if next == 0:
                next = 0.000001
            self.cpf.append(prev + next)
            prev=self.cpf[i]
        
        for i in range(len(self.cpf)):
            self.cpf[i]  = self.cpf[i] / self.cpf[len(self.strategies)-1]
    
    # updates scores when memory changes
    def updateScores(self,pos):
        if pos not in self.scores:
            self.scores[pos] = [0,0,0,0]
        age = self.ageCompensation(pos)
        for i in range(len(self.strategies)):
            temp = 0
            for j in range(len(age)):
                temp += self.strategies[i][j]*age[j]
            self.scores[pos][i] = temp

    # strategy chosen based on cumulative probability function
    def chooseStrategy(self):
        r = np.random.rand()
        for i in range(len(self.cpf)):
            if r<self.cpf[i]:
                return i+1

    # compensates the age of memories by formula y = score * 0.98 ^ (current pole_count - pole_count attached to memory)
    def ageCompensation(self,key):
        result=[]
        for i in range(len(self.memory[key][1])):
            result.append( self.memory[key][0][i] * math.pow(0.98,self.pole_count-self.memory[key][1][i]))
        return result

    # if possible, chooses target pole. Otherwise starts exploring
    def chooseTargetPole(self):
        if self.target != "searching" and self.target != "charge_pole":
            self.prev_target = self.target 
            self.prev_target_pos = self.target_pos
        self.current_strategy = self.chooseStrategy()
        
        options = self.checkOptions()
        
        # if no options, explore
        if len(options) == 0:
            self.target = "searching"
            #completely random position, and not somewhere close to its center
            self.target_pos = (np.random.randint(0,self.model.grid.width), np.random.randint(0, self.model.grid.height))
            self.setDirection()
            #self.newRandomPos()
        else:
            OptionScores = []

            for i in np.arange(np.shape(options)[0]):
                # adding weight to distance & battery and calculating new score for every pole
                dist = abs(self.pos[0]-self.pos[1]) + abs(options[i][0][0]-options[i][0][1])
                a = 1 / 100
                w_dist = (-a * dist) + 1
                w_batt = (-a * self.battery)+1
                new_CP_score = (w_dist - (w_batt * (dist/100)))* options[i][1]

                # adding these new scores to an array
                OptionScores.append(new_CP_score)

            # choosing the pole with the highest score from the array as the new target
            ind_highest_score = np.argmax(OptionScores)
            self.target_pos = options[ind_highest_score][0]
            self.setDirection()
            self.target = "charge_pole"

    # goes through known poles and checks if they're options as targets
    def checkOptions(self):
        # get scores for current strategy
        num=0
        options = []
        for key in self.scores:
            options.append([key,self.scores[key][self.current_strategy-1]])
            num += 1
        # check whether any of the scores are 'off limits'
        found = 0
        if num>0:
            for opt in options:
                if opt[0] in self.offLimits:
                    options.remove(opt)
                else: 
                    distance = (abs(self.pos[0] - opt[0][0]),abs(self.pos[1] - opt[0][1]))
                    battery_required = (max(distance)+0.41421356237*min(distance)) * 0.3 # I'm not sure this is correct. I want it to be the maximum battery use for a 'straight' step
                    if battery_required > self.battery:
                        options.remove(opt)
        return options
            
    # function to decrease battery with the distance
    def use_battery(self):
        dist = (distance.euclidean(self.pos, self.new_position))
        if dist > 0.5*self.model.grid.width:
            dist = self.model.grid.width - dist

        # average battery cost per km is between 0.08 and 0.3 kwh
        cost = dist * ((0.30 - 0.08) * np.random.random_sample() + 0.08)
        self.battery -= cost
    
    def step(self):
        if self.battery <= 0:
            # write data to output
            #print("removing agent")
            self.model.grid._remove_agent(self.pos, self)
            self.model.schedule.remove(self)
            self.model.current_EVs -= 1
        if self.battery > 0:
            self.move()
