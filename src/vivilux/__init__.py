'''
A library for Hebbian-like learning implementations on MZI meshes based on the
work of O'Reilly et al. [1] in computational neuroscience (see https://github.com/emer/leabra).

REFERENCES:
[1] O'Reilly, R. C., Munakata, Y., Frank, M. J., Hazy, T. E., and
    Contributors (2012). Computational Cognitive Neuroscience. Wiki Book,
    4th Edition (2020). URL: https://CompCogNeuro.org

[2] R. C. O'Reilly, “Biologically Plausible Error-Driven Learning Using
    Local Activation Differences: The Generalized Recirculation Algorithm,”
    Neural Comput., vol. 8, no. 5, pp. 895-938, Jul. 1996, 
    doi: 10.1162/neco.1996.8.5.895.
'''

from __future__ import annotations
from collections.abc import Iterator
import math

import numpy as np

from vivilux.activations import Sigmoid
from vivilux.learningRules import CHL
np.random.seed(seed=0)

# import defaults
from .activations import Sigmoid
from .metrics import RMSE
from .learningRules import CHL
from .optimizers import Simple
from .visualize import Monitor

# library default constants
DELTA_TIME = 0.1
DELTA_Vm = DELTA_TIME/2.81
MAX = 1
MIN = 0

class Net:
    '''Base class for neural networks with Hebbian-like learning
    '''
    count = 0
    def __init__(self, layers: list[Layer], meshType: Mesh,
                 metric = RMSE, name = None,
                 optimizer = Simple,
                 optArgs = {},
                 meshArgs = {},
                 numTimeSteps = 50,
                 monitoring = False,
                 defMonitor = Monitor,
                 **kwargs):
        '''Instanstiates an ordered list of layers that will be
            applied sequentially during inference.
        '''
        self.DELTA_TIME = DELTA_TIME
        self.numTimeSteps = numTimeSteps
        self.monitoring = monitoring
        self.defMonitor = defMonitor

        self.name =  f"NET_{Net.count}" if name == None else name
        Net.count += 1

        # TODO: allow different mesh types between layers
        self.layers = layers
        self.metrics = [metric] if not isinstance(metric, list) else metric

        if monitoring: 
            index, layer = 0, self.layers[0]
            layer.monitor = self.defMonitor(name = self.name + ": " + layer.name,
                                    labels = ["time step", "activity"],
                                    limits=[numTimeSteps, 2],
                                    numLines=len(layer))

        for index, layer in enumerate(self.layers[1:], 1):
            size = len(layer)
            layer.addMesh(meshType(size, self.layers[index-1],
                                   **meshArgs))
            layer.optimizer = optimizer(**optArgs)
            if monitoring:
                layer.monitor = self.defMonitor(name = self.name + ": " + layer.name,
                                    labels = ["time step", "activity"],
                                    limits=[numTimeSteps, 2],
                                    numLines=len(layer))

    def Predict(self, data):
        '''Inference method called 'prediction' in accordance with a predictive
            error-driven learning scheme of neural network computation.
        '''
        #Clamp input layer, set minus phase history
        self.layers[0].Clamp(data, monitoring=self.monitoring)
        self.layers[0].phaseHist["minus"][:] = self.layers[0].getActivity()

        for layer in self.layers[1:-1]:
            layer.Predict(monitoring=self.monitoring)
            
        output = self.layers[-1].Predict(monitoring=self.monitoring)
        
        
        return output

    def Observe(self, inData, outData):
        '''Training method called 'observe' in accordance with a predictive
            error-driven learning scheme of neural network computation.
        '''
        #Clamp input layer, set minus phase history
        inLayer = self.layers[0]
        inLayer.Clamp(inData, monitoring=self.monitoring)
        inActivity = inLayer.getActivity()
        inLayer.phaseHist["plus"][:] = inActivity
        deltaPAvg = np.mean(inActivity) - inLayer.ActPAvg
        inLayer.ActPAvg += DELTA_TIME/50*(deltaPAvg) #For updating Gscale
        inLayer.snapshot["deltaPAvg"] = deltaPAvg

        #Clamp output layer, set minus phase history
        outLayer = self.layers[-1]
        outLayer.Clamp(outData, monitoring=self.monitoring)
        outActivity = outLayer.getActivity()
        outLayer.phaseHist["plus"][:] = outActivity
        deltaPAvg = np.mean(outActivity) - outLayer.ActPAvg
        outLayer.ActPAvg += DELTA_TIME/50*(deltaPAvg) #For updating Gscale
        outLayer.snapshot["deltaPAvg"] = deltaPAvg
        
        for layer in self.layers[1:-1]:
            layer.Observe(monitoring=self.monitoring)

        return None # observations know the outcome

    def Infer(self, inData, numTimeSteps=50, reset=False):
        outputData = np.zeros((len(inData), len(self.layers[-1])))
        index = 0
        for inDatum in inData:
            if reset: self.resetActivity()
            for time in range(numTimeSteps):
                result = self.Predict(inDatum)
            outputData[index][:] = result
            index += 1
        return outputData

    
    def Learn(self, inData: np.ndarray, outData: np.ndarray,
              numTimeSteps = None, numEpochs=50, batchSize = 1, repeat=1,
              verbose = False, reset = False, shuffle = True):
        '''Control loop for learning based on GeneRec-like algorithms.
                inData      : input data
                outData     : 
                verbose     : if True, prints net each iteration
                reset       : if True, resets activity between each input sample
        '''
        # allow update of numTimeSteps
        if numTimeSteps is not None:
            self.numTimeSteps = numTimeSteps

        # isolate input and output data
        # inData = deepcopy(inData)
        # outData = deepcopy(outData)

        results = [np.zeros(numEpochs+1) for metric in self.metrics]
        index = 0
        numSamples = len(inData)

        inData = inData.reshape(-1,1) if len(inData.shape) == 1 else inData
        outData = outData.reshape(-1,1) if len(outData.shape) == 1 else outData

        # Temporarily pause monitoring
        monitoring = self.monitoring
        self.monitoring = False
        # Evaluate without training
        print(f"Progress [{self.name}]:")
        print(f"Epoch: 0, sample: ({index}/{numSamples}), metric[{self.metrics[0].__name__}] = {results[0][0]:0.2f}  ", end="\r")
        firstResult = self.Evaluate(inData, outData, self.numTimeSteps, reset)
        for indexMetric, metric in enumerate(self.metrics):
            results[indexMetric][0] = firstResult[indexMetric]
        print(f"Epoch: 0, sample: ({index}/{numSamples}), metric[{self.metrics[0].__name__}] = {results[0][0]:0.2f}  ", end="\r")
        # Unpause monitoring
        self.monitoring = monitoring

        epochResults = np.zeros((len(outData), len(self.layers[-1])))
        # epochResults = np.zeros((len(outData), repeat, len(self.layers[-1])))
        # add mechanism for repetitions

        # batch mode
        if batchSize > 1:
            for layer in self.layers:
                layer.batchMode = True
        
        for epoch in range(numEpochs):
            if shuffle:
                permute = np.random.permutation(len(inData))
                inData, outData = inData[permute], outData[permute]
            index=0
            if batchSize > 1:
                batchInData = [inData[batchSize*i:batchSize*(i+1)] for i in range(math.ceil(len(inData)/batchSize))]
                batchOutData = [outData[batchSize*i:batchSize*(i+1)] for i in range(math.ceil(len(outData)/batchSize))]
            else:
                batchInData = inData.reshape(1,*inData.shape)
                batchOutData = outData.reshape(1,*outData.shape)
            # iterate through data and time
            for inBatch, outBatch in zip(batchInData, batchOutData):
                for inDatum, outDatum in zip(inBatch, outBatch):
                    for iteration in range(repeat):
                        if reset: self.resetActivity()
                        # TODO: MAKE ACTIVATIONS CONTINUOUS
                        ### Data should instead be recorded and labeled at the end of each phase
                        for time in range(self.numTimeSteps):
                            lastResult = self.Predict(inDatum)
                        epochResults[index][:] = lastResult
                        index += 1
                        for time in range(self.numTimeSteps):
                            self.Observe(inDatum, outDatum)
                        # update meshes
                        for layer in self.layers:
                            layer.Learn()
                    print(f"Epoch: ({epoch}/{numEpochs}), sample: ({index}/{numSamples}), metric[{self.metrics[0].__name__}] = {results[0][epoch]:0.4f}  ", end="\r")
            if batchSize > 1: # batched mode
                for layer in self.layers:
                    layer.Learn(batchComplete=True)
            # evaluate metric
            # Record multiple metrics
            for indexMetric, metric in enumerate(self.metrics):
                results[indexMetric][epoch+1] = metric(epochResults, outData)
            print(f"Epoch: ({epoch}/{numEpochs}), sample: ({index}/{numSamples}), metric[{self.metrics[0].__name__}] = {results[0][epoch+1]:0.4f}  ", end="\r")
            if verbose: print(self)
        print("\n")
        # Unpack result if there is only one metric (for backward compatibility)
        if len(results) == 1:
            return results[0]
        return results
    
    def Evaluate(self, inData, outData, numTimeSteps=25, reset=False):
        results = self.Infer(inData, numTimeSteps, reset)

        return [metric(results, outData) for metric in self.metrics]

    def getWeights(self, ffOnly = True):
        weights = []
        for layer in self.layers:
            for mesh in layer.excMeshes:
                weights.append(mesh.get())
                if ffOnly: break
        return weights
    
    def printActivity(self):
        for layer in self.layers:
            "\n".join(layer.printActivity())

    def resetActivity(self):
        for layer in self.layers:
            layer.resetActivity()

    def setLearningRule(self, rule, layerIndex: int = -1):
        '''Sets the learning rule for all forward meshes to 'rule'.
        '''
        if layerIndex == -1 :
            for layer in self.layers:
                layer.rule = rule
        else:
            self.layers[layerIndex].rule = rule

    def __str__(self) -> str:
        strs = []
        for layer in self.layers:
            strs.append(str(layer))

        return "\n\n".join(strs)

class Mesh:
    '''Base class for meshes of synaptic elements.
    '''
    count = 0
    def __init__(self, size: int, inLayer: Layer,
                 **kwargs):
        self.size = size if size > len(inLayer) else len(inLayer)
        # self.matrix = np.eye(self.size)
        # Glorot uniform initialization
        glorotUniform = np.sqrt(6)/np.sqrt(2*size)
        self.matrix = 2*glorotUniform*np.random.rand(self.size, self.size)-glorotUniform
        self.Gscale = 1/len(inLayer)
        self.inLayer = inLayer

        # flag to track when matrix updates (for nontrivial meshes like MZI)
        self.modified = False

        self.name = f"MESH_{Mesh.count}"
        Mesh.count += 1

        self.trainable = True

    def set(self, matrix):
        self.modified = True
        self.matrix = matrix

    def setGscale(self, avgActP):
        #calculate average number of active neurons in sending layer
        sendLayActN = np.maximum(np.round(avgActP*len(self.inLayer)), 1)
        sc = 1/sendLayActN # TODO: implement relative importance
        self.Gscale = sc

    def get(self):
        return self.matrix
    
    def getInput(self):
        return self.inLayer.getActivity()

    def apply(self):
        data = self.getInput()
        # guarantee that data can be multiplied by the mesh
        data = np.pad(data[:self.size], (0, self.size - len(data)))
        return self.applyTo(data)
            
    def applyTo(self, data):
        try:
            return self.get() @ data
        except ValueError as ve:
            print(f"Attempted to apply {data} (shape: {data.shape}) to mesh "
                  f"of dimension: {self.matrix}")

    def Update(self, delta: np.ndarray):
        m, n = delta.shape
        self.modified = True
        # self.matrix[:m, :n] += self.rate*delta
        self.matrix[:m, :n] += delta

    def __len__(self):
        return self.size

    def __str__(self):
        return f"\n\t\t{self.name.upper()} ({self.size} <={self.inLayer.name}) = {self.get()}"

class fbMesh(Mesh):
    '''A class for feedback meshes based on the transpose of another mesh.
    '''
    def __init__(self, mesh: Mesh, inLayer: Layer, fbScale = 0.5) -> None:
        super().__init__(mesh.size, inLayer)
        self.name = "TRANSPOSE_" + mesh.name
        self.mesh = mesh

        self.fbScale = fbScale

        self.trainable = False

    def set(self):
        raise Exception("Feedback mesh has no 'set' method.")

    def get(self):
        self.setGscale(self.inLayer.ActPAvg)
        return self.fbScale * self.mesh.Gscale * self.mesh.get().T 
    
    def getInput(self):
        return self.mesh.inLayer.outAct

    def Update(self, delta):
        return None
    
    
class InhibMesh(Mesh):
    '''A class for inhibitory feedback mashes based on fffb mechanism.
        Calculates inhibitory input to a layer based on a mixture of its
        existing activation and current input.
    '''
    FF = 1
    FB = 1
    FBTau = 1/1.4
    FF0 = 0.1
    Gi = 1.8

    def __init__(self, ffmesh: Mesh, inLayer: Layer) -> None:
        self.name = "FFFB_" + ffmesh.name
        self.ffmesh = ffmesh
        self.size = len(inLayer)
        self.inLayer = inLayer
        self.fb = 0
        self.inhib = np.zeros(self.size)

        self.trainable = False

    def apply(self):
        # guarantee that data can be multiplied by the mesh
        ffAct = self.ffmesh.apply()[:len(self)]
        ffAct = np.pad(ffAct, (0, self.size - len(ffAct)))
        ffAct = np.maximum(ffAct-InhibMesh.FF0,0)

        self.fb += InhibMesh.FBTau * (np.mean(self.inLayer.outAct) - self.fb)

        self.inhib[:] = InhibMesh.FF * ffAct + InhibMesh.FB * self.fb
        return InhibMesh.Gi * self.inhib

    def set(self):
        raise Exception("InhibMesh has no 'set' method.")

    def get(self):
        return self.apply()
    
    def getInput(self):
        return self.mesh.inLayer.outAct

    def Update(self, delta):
        return None

class AbsMesh(Mesh):
    '''A mesh with purely positive weights to mimic biological 
        weight strengths. Positive weighting is enforced by absolute value. 
        Negative connections must be labeled at the neuron group level.
    '''
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.matrix = np.abs(self.matrix)
        self.name = "ABS_" + self.name

    def set(self, matrix):
        super().set(matrix)
        self.matrix = np.abs(self.matrix)


    def Update(self, delta: np.ndarray):
        super().Update(delta)
        self.matrix = np.abs(self.matrix)



class SoftMesh(Mesh):
    '''A mesh with purely positive bounded weights (0 < w < 1) to mimic biological 
        weight strengths. Positive weighting is enforced by soft bounding. Negative
        connections must be labeled at the neuron group level. 
    '''
    def __init__(self, size: int, inLayer: Layer, Inc = 1, Dec = 1,
                 **kwargs):
        self.size = size if size > len(inLayer) else len(inLayer)
        # Glorot uniform initialization
        self.matrix = np.random.rand(self.size, self.size)
        self.Gscale = 1/len(inLayer)
        self.inLayer = inLayer

        # flag to track when matrix updates (for nontrivial meshes like MZI)
        self.modified = False

        self.name = f"MESH_{Mesh.count}"
        Mesh.count += 1

        self.trainable = True

        self.name = "SOFT_" + self.name
        self.Inc = Inc
        self.Dec = Dec

        # Sanity check
        assert(self.matrix.max() < 1)
        assert(self.matrix.min() > 0)

    # def get(self):
    #     mat =  self.matrix
    #     return 1/(1+np.exp(-3*mat))

    def Update(self, delta: np.ndarray):
        mat = self.get()
        # mm, mn = mat.shape
        m, n = delta.shape
        ones = -0.1*np.ones(self.matrix.shape) # OR decay unnecessary weights to zero
        ones[:m, :n] = delta
        delta = ones
        mask = delta > 0
        softBound = np.multiply(mask, (self.Inc*(1-mat))) + np.multiply(np.logical_not(mask), (self.Dec*mat))
        # delta = np.pad(delta, [[0, mm-m], [0, mn-n]]) # zero pad delta matrix
        # delta[:] = np.multiply(delta,softBound[:m, :n]) # OR clip softBound to match delta
        delta[:] = np.multiply(delta,softBound)
        super().Update(delta)
        # bound weights within stable range
        self.matrix = np.minimum(self.matrix, 1)
        self.matrix = np.maximum(self.matrix, 0)
        # assert(self.matrix.max() < 1)
        # assert(self.matrix.min() > 0)
    
class Layer:
    '''Base class for a layer that includes input matrices and activation
        function pairings. Each layer retains a seperate state for predict
        and observe phases, along with a list of input meshes applied to
        incoming data.
    '''
    count = 0
    def __init__(self, length, activation=Sigmoid(), learningRule=CHL,
                 isInput = False, freeze = False, batchMode=False, name = None):
        self.modified = False 
        self.act = activation
        self.rule = learningRule
        
        self.monitor = None
        self.snapshot = {}

        self.batchMode = batchMode
        self.deltas = [] # only used during batched training

        # Initialize layer activities
        self.excAct = np.zeros(length) # linearly integrated dendritic inputs (internal Activation)
        self.inhAct = np.zeros(length)
        self.potential = np.zeros(length)
        self.outAct = np.zeros(length)
        self.modified = True
        # Empty initial excitatory and inhibitory meshes
        self.excMeshes: list[Mesh] = []
        self.inhMeshes: list[Mesh] = [] 
        self.phaseHist = {"minus": np.zeros(length),
                          "plus": np.zeros(length)
                          }
        self.ActPAvg = np.mean(self.outAct) # initialize for Gscale
        self.getActivity() #initialize outgoing Activation

        self.optimizer = Simple()
        self.isInput = isInput
        self.freeze = False
        self.name =  f"LAYER_{Layer.count}" if name == None else name
        if isInput: self.name = "INPUT_" + self.name


        Layer.count += 1

    def getActivity(self, modify = False):
        if self.modified == True or modify:
            self += -DELTA_TIME*self.excAct
            self.Integrate()
            # Calculate output activity
            self.outAct[:] = self.act(self.excAct)


            self.modified = False
        return self.outAct

    def printActivity(self):
        return [self.excAct, self.outAct]
    
    def resetActivity(self):
        '''Resets all activation traces to zero vectors.'''
        length = len(self)
        self.excAct = np.zeros(length)
        self.inhAct = np.zeros(length)
        self.outAct = np.zeros(length)

    def Integrate(self):
        for mesh in self.excMeshes:
            self += DELTA_TIME * mesh.apply()[:len(self)]

        for mesh in self.inhMeshes:
            self += -DELTA_TIME * mesh.apply()[:len(self)]

    def Predict(self, monitoring = False):
        activity = self.getActivity(modify=True)
        self.phaseHist["minus"][:] = activity
        # self.magHistory.append(np.sqrt(np.sum(np.square(activity))))
        if monitoring:
            self.snapshot.update({"activity": activity,
                        "excAct": self.excAct,
                        "inhAct": self.inhAct,
                        })
            self.monitor.update(self.snapshot)
        return activity.copy()

    def Observe(self, monitoring = False):
        activity = self.getActivity(modify=True)
        deltaPAvg = np.mean(activity) - self.ActPAvg
        self.ActPAvg += DELTA_TIME/50*(deltaPAvg) #For updating Gscale
        self.snapshot["deltaPAvg"] = deltaPAvg
        self.phaseHist["plus"][:] = activity
        if monitoring:
            self.snapshot.update({"activity": activity,
                        "excAct": self.excAct,
                        "inhAct": self.inhAct,
                        })
            self.monitor.update(self.snapshot)
        return activity.copy()

    def Clamp(self, data, monitoring = False):
        self.excAct[:] = data[:len(self)]
        self.inhAct[:] = data[:len(self)]
        self.outAct[:] = data[:len(self)]
        if monitoring:
            self.snapshot.update({"activity": data,
                        "excAct": self.excAct,
                        "inhAct": self.inhAct,
                        })
            self.monitor.update(self.snapshot)

    def Learn(self, batchComplete=False):
        if self.isInput or self.freeze: return
        for mesh in self.excMeshes:
            if not mesh.trainable: continue
            inLayer = mesh.inLayer # assume first mesh as input
            delta = self.rule(inLayer, self)
            self.snapshot["delta"] = delta
            if self.batchMode:
                self.deltas.append(delta)
                if batchComplete:
                    delta = np.mean(self.deltas, axis=0)
                    self.deltas = []
                else:
                    return # exit without update for batching
            optDelta = self.optimizer(delta)
            mesh.Update(optDelta)
        
    def Freeze(self):
        self.freeze = True

    def Unfreeze(self):
        self.freeze = False
    
    def addMesh(self, mesh, excitatory = True):
        if excitatory:
            self.excMeshes.append(mesh)
        else:
            self.inhMeshes.append(mesh)

    def __add__(self, other):
        self.modified = True
        return self.excAct + other
    
    def __radd__(self, other):
        self.modified = True
        return self.excAct + other
    
    def __iadd__(self, other):
        self.modified = True
        self.excAct += other
        return self
    
    def __sub__(self, other):
        self.modified = True
        return self.inhAct + other
    
    def __rsub__(self, other):
        self.modified = True
        return self.inhAct + other
    
    def __isub__(self, other):
        self.modified = True
        self.inhAct += other
        return self
    
    def __len__(self):
        return len(self.excAct)

    def __str__(self) -> str:
        layStr = f"{self.name} ({len(self)}): \n\tActivation = {self.act}\n\tLearning"
        layStr += f"Rule = {self.rule}"
        layStr += f"\n\tMeshes: " + "\n".join([str(mesh) for mesh in self.excMeshes])
        layStr += f"\n\tActivity: \n\t\t{self.excAct},\n\t\t{self.outAct}"
        return layStr
    
class ConductanceLayer(Layer):
    '''A layer type with a conductance based neuron model.'''
    def __init__(self, length, activation=Sigmoid(), learningRule=CHL, isInput=False, freeze=False, name=None):
        super().__init__(length, activation, learningRule, isInput, freeze, name)

    def getActivity(self, modify = False):
        if self.modified == True or modify:
            self += -DELTA_TIME * self.excAct
            self -= -DELTA_TIME * self.inhAct
            self.Integrate()
            # Conductance based integration
            excCurr = self.excAct*(MAX-self.outAct)
            inhCurr = self.inhAct*(MIN - self.outAct)
            self.potential[:] -= DELTA_TIME * self.potential
            self.potential[:] += DELTA_TIME * ( excCurr + inhCurr )
            # Calculate output activity
            self.outAct[:] = self.act(self.potential)

            self.snapshot["potential"] = self.potential
            self.snapshot["excCurr"] = excCurr
            self.snapshot["inhCurr"] = inhCurr

            self.modified = False
        return self.outAct
    
    def Integrate(self):
        for mesh in self.excMeshes:
            self += DELTA_TIME * mesh.apply()[:len(self)]

        for mesh in self.inhMeshes:
            self -= DELTA_TIME * mesh.apply()[:len(self)]

class GainLayer(ConductanceLayer):
    '''A layer type with a onductance based neuron model and a layer normalization
        mechanism that multiplies activity by a gain term to normalize the output vector.
    '''
    def __init__(self, length, activation=Sigmoid(), learningRule=CHL,
                 isInput=False, freeze=False, name=None, gainInit = 1, homeostaticMag = 1):
        self.gain = gainInit
        self.homeostaticMag = homeostaticMag
        super().__init__(length, activation, learningRule, isInput, freeze, name)

    def getActivity(self, modify = False):
        if self.modified == True or modify:
            self += -DELTA_TIME * self.excAct
            self -= -DELTA_TIME * self.inhAct
            self.Integrate()
            # Conductance based integration
            excCurr = self.excAct*(MAX-self.outAct)
            inhCurr = self.inhAct*(MIN - self.outAct)
            self.potential[:] -= DELTA_TIME * self.potential
            self.potential[:] += self.homeostaticMag * DELTA_TIME * ( excCurr + inhCurr )
            activity = self.act(self.potential)
            #TODO: Layer Normalization
            self.gain -= DELTA_TIME * self.gain
            self.gain += DELTA_TIME / np.sqrt(np.sum(np.square(activity)))
            # Calculate output activity
            self.outAct[:] = self.gain * activity

            self.snapshot["potential"] = self.potential
            self.snapshot["excCurr"] = excCurr
            self.snapshot["inhCurr"] = inhCurr
            self.snapshot["gain"] = self.gain

            self.modified = False
        return self.outAct

class SlowGainLayer(ConductanceLayer):
    '''A layer type with a onductance based neuron model and a layer normalization
        mechanism that multiplies activity by a gain term to normalize the output
        vector. Gain mechanism in this neuron model is slow and is learned using
        the average magnitude over the epoch.
    '''
    def __init__(self, length, activation=Sigmoid(), learningRule=CHL,
                 isInput=False, freeze=False, name=None, gainInit = 1, homeostaticMag = 1, **kwargs):
        self.gain = gainInit
        self.homeostaticMag = homeostaticMag
        self.magHistory = []
        super().__init__(length, activation=activation, learningRule=learningRule, isInput=isInput, freeze=freeze, name=name, **kwargs)

    def getActivity(self, modify = False):
        if self.modified == True or modify:
            self += -DELTA_TIME * self.excAct
            self -= -DELTA_TIME * self.inhAct
            self.Integrate()
            # Conductance based integration
            excCurr = self.excAct*(MAX-self.outAct)
            inhCurr = self.inhAct*(MIN - self.outAct)
            self.potential[:] -= DELTA_TIME * self.potential
            self.potential[:] += self.homeostaticMag * DELTA_TIME * ( excCurr + inhCurr )
            activity = self.act(self.potential)
            
            # Calculate output activity
            self.outAct[:] = self.gain * activity

            self.snapshot["potential"] = self.potential
            self.snapshot["excCurr"] = excCurr
            self.snapshot["inhCurr"] = inhCurr
            self.snapshot["gain"] = self.gain

            self.modified = False
        return self.outAct
    
    def Predict(self, monitoring = False):
        activity = self.getActivity(modify=True)
        self.phaseHist["minus"][:] = activity
        self.magHistory.append(np.sqrt(np.sum(np.square(activity))))
        if monitoring:
            self.snapshot.update({"activity": activity,
                        "excAct": self.excAct,
                        "inhAct": self.inhAct,
                        })
            self.monitor.update(self.snapshot)
        return activity.copy()
    
    def Learn(self):
        super().Learn()
        if self.batchComplete:
            # Set gain
            self.gain = self.homeostaticMag/np.mean(self.magHistory)
            self.magHistory = [] # clear history


class RateCode(Layer):
    '''A layer type which assumes a rate code proportional to excitatory 
        conductance minus threshold conductance.'''
    def __init__(self, length, activation=Sigmoid(), learningRule=CHL,
                 threshold = 0.5, revPot=[0.3, 1, 0.25], conductances = [0.1, 1, 1],
                 isInput=False, freeze=False, name=None):
        
        # Set hyperparameters relevant to rate coding
        self.threshold = threshold # threshold voltage

        self.revPotL = revPot[0]
        self.revPotE = revPot[1]
        self.revPotI = revPot[2]

        self.leakCon = conductances[0] # leak conductance
        self.excCon = conductances[1] # scaling of excitatory conductance
        self.inhCon = conductances[2] # scaling of inhibitory conductance
        super().__init__(length, activation, learningRule, isInput, freeze, name)
        self.snapshot["totalCon"] = self.excAct
        self.snapshot["thresholdCon"] = self.excAct
        self.snapshot["inhCurr"] = self.excAct

    def getActivity(self, modify = False):
        if self.modified == True or modify:
            # Settling dynamics of the excitatory/inhibitory conductances
            self.Integrate()

            # Calculate threshold conductance
            inhCurr = self.inhAct*self.inhCon*(self.threshold-self.revPotI)
            leakCurr = self.leakCon*(self.threshold-self.revPotL)
            thresholdCon = (inhCurr+leakCurr)/(self.revPotE-self.threshold)

            # Calculate rate of firing from excitatory conductance
            deltaOut = DELTA_TIME*(self.act(self.excAct*self.excCon - thresholdCon)-self.outAct)
            self.outAct[:] += deltaOut
            
            # Store snapshots for monitoring
            self.snapshot["excAct"] = self.excAct
            self.snapshot["totalCon"] = self.excAct-thresholdCon
            self.snapshot["thresholdCon"] = thresholdCon
            self.snapshot["inhCurr"] = inhCurr
            self.snapshot["deltaOut"] = deltaOut # to determine convergence

            self.modified = False
        return self.outAct
    
    def Integrate(self):
        # self.excAct[:] -= DELTA_TIME*self.excAct
        # self.inhAct[:] -= DELTA_TIME*self.inhAct
        self.excAct[:] = 0
        self.inhAct[:] = 0
        for mesh in self.excMeshes:
            # self += DELTA_TIME * mesh.apply()[:len(self)]
            self += mesh.apply()[:len(self)]

        for mesh in self.inhMeshes:
            # self -= DELTA_TIME * mesh.apply()[:len(self)]
            self -= mesh.apply()[:len(self)]


class RecurNet(Net):
    '''A recurrent network with feed forward and feedback meshes
        between each layer. Based on ideas presented in [2].
    '''
    def __init__(self, *args, FeedbackMesh = fbMesh, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for index, layer in enumerate(self.layers[1:-1], 1): 
            #skip input and output layers, add feedback matrices
            nextLayer = self.layers[index+1]
            layer.addMesh(FeedbackMesh(nextLayer.excMeshes[0], nextLayer))

class FFFB(Net):
    '''A recurrent network with feed forward and feedback meshes
        and a trucated lateral inhibition mechanism. Based on 
        ideas presented in [1].
    '''
    def __init__(self, *args, FeedbackMesh = fbMesh, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for index, layer in enumerate(self.layers[1:-1], 1): #skip input and output layers
            # add feedback matrices
            nextLayer = self.layers[index+1]
            layer.addMesh(FeedbackMesh(nextLayer.excMeshes[0], nextLayer))
            # add FFFB inhibitory mesh
            inhibitoryMesh = InhibMesh(layer.excMeshes[0], layer)
            layer.addMesh(inhibitoryMesh, excitatory=False)
        # add last layer FFFB mesh
        layer = self.layers[-1]
        inhibitoryMesh = InhibMesh(layer.excMeshes[0], layer)
        layer.addMesh(inhibitoryMesh, excitatory=False)


if __name__ == "__main__":
    from .learningRules import GeneRec
    
    from sklearn import datasets
    import matplotlib.pyplot as plt

    net = FFFB([
        Layer(4, isInput=True),
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

    result = net.Learn(inputs, targets, numEpochs=500)
    plt.plot(result)
    plt.show()