### agents.py

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
        self.free_poles = 2        

    def step(self):
        pass
        max_charge = 3*model.vision
        max_sockets = 2
        self.charge = max_charge
        self.max_sockets = max_sockets
        self.pos = pos
        

    def step(self):
        self.amount = min([self.max_sockets, self.amount + 1])


# Create the Electric Vehicles agents
class EV_Agent(Agent):
    """ An agent with fixed initial battery."""

    def __init__(self, unique_id, model, vision, home_pos, work_pos):
        super().__init__(unique_id, model)
        self.unique_id = unique_id
        self.vision = 1                                                    # taken from a slider input
        self.max_battery = np.random.randint(150,200)                      # maximum battery size, differs for different cars
        self.battery = np.random.randint(120,self.max_battery)             # starting battery 
        self.usual_charge_time = 10                                        # the time period for how long it usually charges
        self.time_charging = 0
        self.current_strategy = 0
        self.pole_count = 0                                                # counts the amount of charging_pole encounters (to calculate the 'age' of memories)
        self.strategies = [[1,1,1,1,1,1,1,1,1,1],[1,1,1,1,1,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0]] # different strategies used, which memories count in each strategyg
        self.initMemory() 
        self.possible_steps = []
        self.offLimits = []
        self.prev_target = ""
        self.prev_target_pos = []
        self.home_pos = home_pos            # Agent lives here
        self.work_pos = work_pos            # Agent works here
        self.shopping_pos = (0, 0)          # Will be set later
        self.target = "work"                # Sets off from home at first
        self.target_pos = self.work_pos[:]
        self.braveness = 1

    # can randomly move in the neighbourhood with radius = vision
    def move(self):
        self.checkTargets()
        if not (self.target == "charge_pole" and self.pos == self.target_pos):
            self.getNeighbourhood()
            self.chooseNextStep()
            self.moveEV()
            
        
    def getNeighbourhood(self):
        self.possible_steps = self.model.grid.get_neighborhood(self.pos,radius = 1,moore=True,include_center=True)
        self.polesInSight = self.checkForPoles()

        done = False
        neighbors = []
        for point in self.polesInSight:
            if self.inLastPoints(point) == False:
                neighbors.append(point)
                if self.checkIfFree(point)>0:
                    self.updateMemory(1,point)
                    if (self.battery < 50 and done == False) or (self.battery < 100 and self.target != "charge_pole"):
                        if self.target != "charge_pole" and self.target != "searching": 
                            self.prev_target = self.target
                            self.prev_target_pos = self.target_pos
                        self.target_pos = point
                        self.target = "charge_pole"
                        done = True
                else:
                    self.updateMemory(-1,point)
                    if self.battery < 100:
                        if len(self.offLimits) < 4:
                            self.offLimits.append(point)
                        else:
                            self.offLimits = [point]+self.offLimits[:-1]
        self.neighborMemory(neighbors)

    def neighborMemory(self,neighbors):
        self.memory["neighborPoles"] = [neighbors], self.memory["neighborPoles"][:-1]

    def checkForPoles(self):
        poles = []
        cells = self.model.grid.get_neighborhood(self.pos,radius = self.vision,moore=True,include_center=True)
        for cell in cells:
            for agent in self.model.grid.get_cell_list_contents(cell):
                if type(agent) == Charge_pole:
                    poles.append(cell)
        return poles

    def checkIfFree(self,pos):
        for agent in self.model.grid.get_cell_list_contents(pos):
            if type(agent) == Charge_pole:
                if agent.free_poles>2:
                    print("too many poles!!!!", agent.free_poles,pos)
                if agent.free_poles<0:
                    print("too little poles!!!!", agent.free_poles,pos)
                return agent.free_poles

    def takePlace(self):
        for agent in self.model.grid.get_cell_list_contents(self.pos):
            if type(agent) == Charge_pole:
                agent.free_poles = agent.free_poles - 1
                #print(self.pos, "free poles: ", agent.free_poles)

    def freePlace(self):
        for agent in self.model.grid.get_cell_list_contents(self.pos):
            if type(agent) == Charge_pole:
                agent.free_poles = agent.free_poles + 1
                #print(self.pos, "free poles: ", agent.free_poles)

    def inLastPoints(self,pos):
        for timepoint in self.memory["neighborPoles"]:
            for coordinate in timepoint:
                if coordinate == pos:
                    return True
        return False

    def charge(self):
        #print(self.unique_id, self.battery, self.pos)
        self.time_charging = self.time_charging + 1
        if self.time_charging < self.usual_charge_time or self.battery < self.max_battery:
            if self.battery < self.max_battery:
                self.battery += 10
                if self.battery > self.max_battery: 
                    self.battery = self.max_battery
        else: 
            #print("done", self.unique_id, self.battery, self.pos)
            self.target = self.prev_target
            self.target_pos = self.prev_target_pos
            self.time_charging = 0
            self.strategy = 0
            self.offLimits = []
            self.freePlace()

    def checkTargets(self):
        if self.battery < 100 and self.target != "charge_pole" and self.target != "searching":
            self.chooseTargetPole()

        if self.target_pos[0] == self.pos[0] and self.target_pos[1] == self.pos[1]:
            # Target: work -> shopping, shopping -> home, home -> work
            if self.target == "work":
                self.target = "shopping"
                self.newRandomPos()                
            elif self.target == "shopping":
                # Goes home
                self.target = "home"
                self.target_pos = self.home_pos[:]
            elif self.target == "searching":
                self.chooseTargetPole()
            elif self.target == "charge_pole":
                if self.time_charging == 0:
                    if self.checkIfFree(self.pos) > 0:
                        self.takePlace()
                        #print("target reached: charging", self.unique_id)
                        self.charge()
                    else:
                        if len(self.offLimits) < 4:
                            self.offLimits.append(self.pos)
                        else:
                            self.offLimits = [self.pos]+self.offLimits[:-1]
                        self.chooseTargetPole()
                else:
                    self.charge()
            else:
                # Goes to work
                self.target = "work"
                self.target_pos = self.work_pos[:]

    def newRandomPos(self):
        # Coordinates between home and work
        center_pos = ((self.home_pos[0]+self.work_pos[0])/2,
                      (self.home_pos[1]+self.work_pos[1])/2)

        # Random polar coordinates
        rand_angle = np.random.uniform(low=0, high=np.pi*2)
        rand_distance = np.random.uniform(low=0, high=self.braveness)

        # New random target position
        self.target_pos[0] = int(np.clip(a_min=0, a_max=self.model.grid.width, a=center_pos[0]+rand_distance*np.cos(rand_angle)))
        self.target_pos[1] = int(np.clip(a_min=0, a_max=self.model.grid.height, a=center_pos[1] + rand_distance * np.sin(rand_angle)))

    def chooseNextStep(self):
        # Steps towards the target and chooses a position with the shortest remaining distance
        self.new_position = self.possible_steps[0]
        new_distance = distance.euclidean(self.new_position, self.target_pos)
        for candidate_position in self.possible_steps:
            candidate_distance = distance.euclidean(self.target_pos, candidate_position)
            if candidate_distance < new_distance:
                new_distance = candidate_distance
                self.new_position = candidate_position[:]
    
    def moveEV(self):
        self.use_battery()
        self.model.grid.move_agent(self,self.new_position)
    
    def initMemory(self):
        # for each strategy create a (neutral) memory
        self.memory = {}
        self.scores = {}
        for i in range(len(self.strategies)):
            self.memory[i+1]=[[0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0]]
        self.memory["neighborPoles"] = [[0],[0],[0]]
        self.cpf = []
        self.updateStrategies()

    def updateMemory(self,succes,pos):
        self.pole_count += 1
        if pos in self.memory:
            self.memory[pos] = [[succes]+self.memory[pos][0][:-1],[self.pole_count]+self.memory[pos][1][:-1]]
        else:
            self.memory[pos] = [[succes]+[0,0,0,0,0,0,0,0,0],[self.pole_count]+[0,0,0,0,0,0,0,0,0]]
        if self.current_strategy > 0 and pos == self.target_pos:
            self.memory[self.current_strategy] = [[succes]+self.memory[self.current_strategy][0][:-1],[self.pole_count]+self.memory[self.current_strategy][1][:-1]]
        self.updateStrategies()
        self.updateScores(pos)
        
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
    
    def updateScores(self,pos):
        if pos not in self.scores:
            self.scores[pos] = [0,0,0,0]
        age = self.ageCompensation(pos)
        for i in range(len(self.strategies)):
            temp = 0
            for j in range(len(age)):
                temp += self.strategies[i][j]*age[j]
            self.scores[pos][i] = temp

    # call self.current_strategy = self.chooseStrategy() - chosen based on cumulative probability function
    def chooseStrategy(self):
        r = np.random.rand()
        for i in range(len(self.cpf)):
            if i<r:
                return i+1

    def ageCompensation(self,key):
        result=[]
        for i in range(len(self.memory[key][1])):
            result.append( self.memory[key][0][i] * math.pow(0.98,self.pole_count-self.memory[key][1][i]))
        return result

    def chooseTargetPole(self):
        #print("choosing target pole",self.unique_id)
        if self.target != "searching" and self.target != "charge_pole":
            self.prev_target = self.target 
            self.prev_target_pos = self.target_pos
        self.current_strategy = self.chooseStrategy()
        
        options = self.checkOptions()
        
        # if no options, explore
        if len(options) == 0:
            self.target = "searching"
            self.newRandomPos()
        else:
            OptionScores = []

            # The option array is an array with [[position, best sore], [position, best score], ...] depending on how
            # many options are available. In this for loop the distance between every CP and the agent is
            # calculated. This distance is put into a linear declining formula which is multiplied by the already
            # existing score. After every all the multiplications are done, the CP with the best score is chosen as
            # the new target position. We still have to discuss if we want it to be exp. of lin. declining function.
            # (depending on how strong we want the distance to affect the EV)
            for i in np.arange(np.shape(options)[0]):
                dist = abs(self.pos[0]-self.pos[1]) + abs(options[i][0][0]-options[i][0][1])
                a_lin = 1 / 50
                w_dist_lin = (-a_lin * dist) + 1
                new_CP_score = w_dist_lin * options[i][1]
                OptionScores.append(new_CP_score)

            ind_highest_score = np.argmax(OptionScores)
            self.target_pos = options[ind_highest_score][0]
            #self.target_pos = random.choice(options)[0]
            self.target = "charge_pole"
            #print("target set",self.unique_id,self.target_pos)

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
                if opt[0] not in self.offLimits:
                    found += 1
                else: 
                    options.remove(opt)
        print(options)
        if len(options)>0:
            print(options[0])
            print(options[0][0])
        return options
            
    # function to decrease battery with the distance
    def use_battery(self):
        dist = (distance.euclidean(self.pos, self.new_position))
        cost = dist
        self.battery -= cost
    
    def step(self):
        #self.total_EV_in_cell = self.total_EV_in_cell
        if self.battery <= 0:
            self.model.grid._remove_agent(self.pos, self)
            self.model.schedule.remove(self)
        if self.battery > 0:
            self.move()

            #print(self.unique_id, self.battery)

