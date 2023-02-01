'''
A library for Hebbian-like learning implementations on MZI meshes based on the
work of O'Reilly et al. [1] in computation.

REFERENCES:
[1] O'Reilly, R. C., Munakata, Y., Frank, M. J., Hazy, T. E., and
    Contributors (2012). Computational Cognitive Neuroscience. Wiki Book,
    4th Edition (2020). URL: https://CompCogNeuro.org

[2] R. C. O'Reilly, “Biologically Plausible Error-Driven Learning Using
    Local Activation Differences: The Generalized Recirculation Algorithm,”
    Neural Comput., vol. 8, no. 5, pp. 895-938, Jul. 1996, 
    doi: 10.1162/neco.1996.8.5.895.
'''

from collections.abc import Iterator

import numpy as np
from typing import List
np.random.seed(seed=0)

# import defaults
from .activations import Sigmoid
from .metrics import RMSE
from .learningRules import CHL

# library constants
DELTA_TIME = 0.1

class Net:
    '''Base class for neural networks with Hebbian-like learning
    '''
    def __init__(self, layers: List['Layer'], meshType, metric = RMSE, learningRate = 0.1):
        '''Instanstiates an ordered list of layers that will be
            applied sequentially during inference.
        '''
        # TODO: allow different mesh types between layers
        self.layers = layers
        self.metric = metric
        self.learningRate = learningRate
        self.meshType = meshType
        self.number_of_layers = len(layers)
        self.meshes = [np.eye(layers[i+1].length,layers[i].length) for i in range(self.number_of_layers-1)]
        # self.meshes = np.array([np.eye(layers[i+1].length,layers[i].length) for i in range(self.numLayers-1)],dtype=object)



        # for index, layer in enumerate(self.layers[1:]):
        #     size = len(layer)
        #     layer.addMesh(meshType(size, self.layers[index-1], learningRate))

    def minus_phase_one_step(self, input_data):
        '''Inference method called 'prediction' in accordance with a predictive
            error-driven learning scheme of neural network computation.
        '''
        # outputs = []
        self.layers[0].Clamp(input_data)
        # counter_layer = 0
        # print("here0")
        for layer_index in range(1,self.number_of_layers-1):
            # print("here1")
            # counter_layer += 1
            # print(f"{counter_layer=}")
            # layer.Predict()
            layer_Lin_delta = DELTA_TIME * (-1* self.layers[layer_index].Lin + np.abs(self.meshes[layer_index-1] @ self.layers[layer_index-1].Act)**2 + np.abs(self.meshes[layer_index].T @ self.layers[layer_index+1].Act)**2)
            self.layers[layer_index].Lin += layer_Lin_delta
            self.layers[layer_index].Act = self.layers[layer_index].act(self.layers[layer_index].Lin)
            
        last_layer_index = self.number_of_layers-1
        layer_Lin_delta = DELTA_TIME * (-1* self.layers[last_layer_index].Lin + np.abs(self.meshes[last_layer_index-1] @ self.layers[last_layer_index-1].Act)**2)
        self.layers[last_layer_index].Lin += layer_Lin_delta
        self.layers[last_layer_index].Act = self.layers[last_layer_index].act(self.layers[last_layer_index].Lin)
        output = self.layers[last_layer_index].Act
        
        return output
    def save_after_minus_phase(self):
        for layer_index in range(1,self.number_of_layers):
            self.layers[layer_index].preAct = self.layers[layer_index].Act
        return self.layers[self.number_of_layers-1].preAct


    def plus_phase_one_step(self, input_data, output_data):
        '''Training method called 'observe' in accordance with a predictive
            error-driven learning scheme of neural network computation.
        '''
        self.layers[0].Clamp(input_data)
        self.layers[-1].Clamp(output_data)
        for layer_index in range(1,self.number_of_layers-1):
            # print("here1")
            # counter_layer += 1
            # print(f"{counter_layer=}")
            # layer.Predict()
            layer_Lin_delta = DELTA_TIME * (-1* self.layers[layer_index].Lin + np.abs(self.meshes[layer_index-1] @ self.layers[layer_index-1].Act)**2 + np.abs(self.meshes[layer_index].T @ self.layers[layer_index+1].Act)**2)
            self.layers[layer_index].Lin += layer_Lin_delta
            self.layers[layer_index].Act = self.layers[layer_index].act(self.layers[layer_index].Lin)
        
        # last_layer_index = self.number_of_layers-1
        # layer_preLin_delta = DELTA_TIME * (-1* self.layers[last_layer_index].preLin + self.meshes[last_layer_index-1] @ self.layers[last_layer_index-1].preAct**2)
        # self.layers[last_layer_index].preLin += layer_preLin_delta
        # self.layers[last_layer_index].preAct = self.layers[last_layer_index].act(self.layers[last_layer_index].preLin)
        # output = self.layers[last_layer_index].preAct

        # self.layers[-1].Clamp(outData)

        return None # observations know the outcome
    
    def save_after_plus_phase(self):
        for layer_index in range(1,self.number_of_layers):
            self.layers[layer_index].obsAct = self.layers[layer_index].Act

    def Infer(self, inData, numTimeSteps=25):
        for inDatum in inData:
            for time in range(numTimeSteps):
                self.Predict(inDatum)

    def minus_phase_progress(self, input_data, numTimeSteps=50):
        for time in range(numTimeSteps):#>3
            _ = self.minus_phase_one_step(input_data)
        act_minus = self.save_after_minus_phase()
        return act_minus
    def plus_phase_progress(self, input_data, output_data, numTimeSteps=50):
        for time in range(numTimeSteps):#>3
            _ = self.plus_phase_one_step(input_data,output_data)
        self.save_after_plus_phase()

    def Learn(self, inData, outData, numTimeSteps=50, numEpochs=50, verbose = False):
        results = np.zeros(numEpochs)
        epochResults = np.zeros((len(outData), len(self.layers[-1])))
        # for iinx, layer in enumerate(list(self.layers)):
                # print(">> pre-training mesh of layer ", iinx, " is ", layer.meshes[0])
        for epoch in range(numEpochs):
            # iterate through data and time
            index=0
            for inDatum, outDatum in zip(inData, outData): #>1
                #>2
                # for time in range(numTimeSteps):#>3
                #     # if epoch == 0 and index == 0:
                #     #     print("init>time step ",time ," inference of the first data sample: ", self.layers[-2].Act)
                #     _ = self.minus_phase_one_step(inDatum)
                # lastResult = self.save_after_minus_phase()
                lastResult = self.minus_phase_progress(inDatum, numTimeSteps=numTimeSteps)
                    #>4
                # if epoch == 0:
                #     print("init>at sample ",index ," inference of the first data sample: ", lastResult, " (should be close to ", outDatum,")")
                # for time in range(numTimeSteps):#>3
                #     #>5
                #     # if epoch == 0 and index == 0:
                #     #     print("init>time step ",time+51 ," inference of the first data sample: ", self.layers[-2].Act)
                #     self.plus_phase_one_step(inDatum, outDatum)
                #     #>6
                # self.save_after_plus_phase()
                self.plus_phase_progress(inDatum, outDatum, numTimeSteps=numTimeSteps)
                epochResults[index] = lastResult
                index += 1
                if epoch != 0:
                    self.apply_learn()
                    # for layer in self.layers:
                    #     layer.Learn()
            # update meshes
            # if epoch != 0:
            #     for layer in self.layers:
            #         layer.Learn()
            # for iinx, layer in enumerate(list(self.layers)):
            #     print(">>for epoch=",epoch,"mesh of layer ", iinx, " is ", layer.meshes[0])
            # evaluate metric
            results[epoch] = self.metric(epochResults, outData)
            if verbose: print(self)
        
        return results

    def apply_learn(self):
        for mesh_index in range(1,len(self.meshes)): # the architecture is such layer_i <-> mesh <-> layer_j (where j = i+1)
            layer_i_index = mesh_index
            delta = self.layers[layer_i_index].rule(self.layers[layer_i_index], self.layers[layer_i_index+1])
            self.meshes[mesh_index] += self.learningRate*delta


    def getWeights(self):
        weights = []
        for mesh in self.meshes:
            weights.append(mesh)
        return weights

    def setLearningRule(self, rule):
        '''Sets the learning rule for all forward meshes to 'rule'.
        '''
        for layer in self.layers:
            layer.rule = rule

    def __str__(self) -> str:
        strs = []
        for layer in self.layers:
            strs.append(str(layer))

        return str(strs)

class Mesh:
    '''Base class for meshes of synaptic elements.
    '''
    def __init__(self, size: int, inLayer, learningRate=0.5):
        self.size = size if size > len(inLayer) else len(inLayer)
        self.matrix = np.eye(self.size)
        self.inLayer = inLayer
        self.rate = learningRate

    def set(self, matrix):
        self.matrix = matrix

    def get(self):
        return self.matrix

    def apply(self, data):
        try:
            return self.matrix @ data
        except ValueError as ve:
            print(f"Attempted to apply {data} (shape: {data.shape}) to mesh "
                  f"of dimension: {self.matrix}")

    def Predict(self):
        data = self.inLayer.preAct
        return self.apply(data)

    def Observe(self, data=0):
        data = self.inLayer.obsAct
        return self.apply(data)

    def Update(self, delta):
        self.matrix += self.rate*delta

    def __len__(self):
        return self.size

    def __str__(self):
        return f"\n\t\tMesh ({self.size}) = {self.get()}"

class fbMesh(Mesh):
    '''A class for feedback meshes based on the transpose of another mesh.
    '''
    def __init__(self, mesh: Mesh, inLayer) -> None:
        super().__init__(mesh.size, inLayer)
        self.mesh = mesh

    def set(self):
        raise Exception("Feedback mesh has no 'set' method.")

    def get(self):
        return self.mesh.matrix.T

    def apply(self, data):
        matrix = self.mesh.matrix.T
        try:
            return matrix @ data
        except ValueError as ve:
            print(f"Attempted to apply {data} (shape: {data.shape}) to mesh of dimension: {matrix}")

    def Update(self, delta):
        return None

class Layer:
    '''Base class for a layer that includes input matrices and activation
        function pairings. Each layer retains a seperate state for predict
        and observe phases, along with a list of input meshes applied to
        incoming data.
    '''
    def __init__(self, length, activation=Sigmoid, learningRule=CHL):
        self.length = length
        self.Lin = np.zeros(length)
        self.Act = np.zeros(length) 
        self.preAct = np.zeros(length) #minus phase
        self.obsAct = np.zeros(length) #plus phase
        self.act = activation
        self.rule = learningRule
        # self.meshes = [] #empty initial mesh list

    # def addMesh(self, mesh):
    #     self.meshes.append(mesh)

    def Predict(self):
        self.preLin -= DELTA_TIME*self.preLin
        counterr =0
        for mesh in self.meshes:
            counterr +=1
            # print(f"{counterr=}")
            self.preLin += DELTA_TIME * mesh.Predict()[:len(self)]**2
        self.preAct = self.act(self.preLin)
        return self.preAct

    def Observe(self):
        self.obsLin -= DELTA_TIME * self.obsLin
        counterr = 0
        for mesh in self.meshes:
            counterr +=1
            # print(f"{counterr=}")
            self.obsLin += DELTA_TIME * mesh.Observe()[:len(self)]**2
        self.obsAct = self.act(self.obsLin)
        return self.preAct

    def Clamp(self,data):
        self.Act = data[:self.length]

    def Learn(self):
        inLayer = self.meshes[0].inLayer # assume first mesh as input
        delta = self.rule(inLayer, self)
        self.meshes[0].Update(delta)

    def __len__(self):
        return len(self.preAct)

    def __str__(self) -> str:
        str = f"Layer ({len(self)}): \n\tActivation = {self.act}\n\tLearning"
        str += f"Rule = {self.rule}"
        # str += f"\n\tMeshes: {self.meshes}"
        return str

class FFFB(Net):
    '''A network with feed forward and feedback meshes between each
        layer. Based on ideas presented in [2]
    '''
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # for index, layer in enumerate(self.layers[:-1]):
        #     nextLayer = self.layers[index+1]
        #     layer.addMesh(fbMesh(nextLayer.meshes[0], nextLayer))


if __name__ == "__main__":
    from .learningRules import GeneRec
    
    from sklearn import datasets
    import matplotlib.pyplot as plt

    net = FFFB([
        Layer(4, learningRule=GeneRec),
        Layer(4, learningRule=GeneRec)
    ], Mesh)

    iris = datasets.load_iris()
    inputs = iris.data
    maxMagnitude = np.max(np.sqrt(np.sum(np.square(inputs), axis=1)))
    inputs = inputs/maxMagnitude # bound on (0,1]
    targets = np.zeros((len(inputs),4))
    targets[np.arange(len(inputs)), iris.target] = 1
    #shuffle both arrays in the same manner
    shuffle = np.random.permutation(len(inputs))
    inputs, targets = inputs[shuffle], targets[shuffle]

    result = net.Learn(inputs, targets, numEpochs=5000)
    plt.plot(result)
    plt.show()