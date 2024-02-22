'''Defines a Layer class corresponding to a vector of neurons.
'''

# type checking
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .nets import Net
    from .layers import Layer

from .processes import XCAL

import numpy as np


class Mesh:
    '''Base class for meshes of synaptic elements.
    '''
    count = 0
    def __init__(self, 
                 size: int,
                 inLayer: Layer,
                 AbsScale: float = 1,
                 RelScale: float = 1,
                 Off: float = 1,
                 Gain: float = 6,
                 **kwargs):
        self.size = size if size > len(inLayer) else len(inLayer)
        self.Off = Off
        self.Gain = Gain

        # Glorot uniform initialization
        glorotUniform = np.sqrt(6)/np.sqrt(2*size)
        self.matrix = 2*glorotUniform*np.random.rand(self.size, self.size)-glorotUniform
        self.linMatrix = np.copy(self.matrix)
        self.InvSigMatrix()

        # Other initializations
        self.Gscale = 1#/len(inLayer)
        self.inLayer = inLayer
        self.OptThreshParams = inLayer.OptThreshParams
        self.lastAct = np.zeros(self.size)
        self.inAct = np.zeros(self.size)

        # flag to track when matrix updates (for nontrivial meshes like MZI)
        self.modified = False

        self.name = f"MESH_{Mesh.count}"
        Mesh.count += 1

        self.trainable = True
        self.sndActAvg = inLayer.ActAvg
        self.rcvActAvg = None

        self.AbsScale = AbsScale
        self.RelScale = RelScale

    def set(self, matrix):
        self.modified = True
        self.matrix = matrix
        self.InvSigMatrix()

    def setGscale(self):
        # TODO: handle case for inhibitory mesh
        totalRel = np.sum([mesh.RelScale for mesh in self.rcvLayer.excMeshes])
        self.Gscale = self.AbsScale * self.RelScale 
        self.Gscale /= totalRel if totalRel > 0 else 1

        # calculate average from input layer on last trial
        # TODO: temporally integrate this avg activity to match Leabra
        self.avgActP = self.inLayer.ActAvg.ActPAvg

        #calculate average number of active neurons in sending layer
        sendLayActN = np.maximum(np.round(self.avgActP*len(self.inLayer)), 1)
        sc = 1/sendLayActN # TODO: implement relative importance
        self.Gscale *= sc

    def get(self):
        return self.Gscale * self.matrix
    
    def getInput(self):
        return self.inLayer.getActivity()

    def apply(self):
        data = self.getInput()
        # guarantee that data can be multiplied by the mesh
        data = np.pad(data[:self.size], (0, self.size - len(data)))

        # Implement delta-sender behavior (thresholds changes in conductance)
        ## NOTE: this does not reduce matrix multiplications like it does in Leabra
        delta = data - self.lastAct

        cond1 = data <= self.OptThreshParams["Send"]
        cond2 = np.abs(delta) <= self.OptThreshParams["Delta"]
        mask1 = np.logical_or(cond1, cond2)
        notMask1 = np.logical_not(mask1)
        delta[mask1] = 0 # only signal delta above both thresholds
        self.lastAct[notMask1] = data[notMask1]

        cond3 = self.lastAct > self.OptThreshParams["Send"]
        mask2 = np.logical_and(cond3, cond1)
        delta[mask2] = -self.lastAct[mask2]
        self.lastAct[mask2] = 0

        self.inAct[:] += delta
        
        return self.applyTo(self.inAct)
            
    def applyTo(self, data):
        try:
            return np.array(self.get() @ data).reshape(-1) # TODO: check for slowdown from this trick to support single-element layer
        except ValueError as ve:
            print(f"Attempted to apply {data} (shape: {data.shape}) to mesh "
                  f"of dimension: {self.get().shape}")
            print(ve)

    def AttachLayer(self, rcvLayer: Layer):
        self.XCAL = XCAL() #TODO pass params from layer or mesh config
        self.XCAL.AttachLayer(self.inLayer, rcvLayer)
        rcvLayer.phaseProcesses.append(self.XCAL) # Add XCAL as phasic process to layer
        self.rcvLayer = rcvLayer

    def Update(self,
               # delta: np.ndarray ### Now delta is handled by the 
               ):
        # self.modified = True
        # self.matrix[:m, :n] += self.rate*delta

        delta = self.XCAL.GetDeltas()
        m, n = delta.shape
        self.linMatrix[:m, :n] += delta
        self.SigMatrix()

    def SigMatrix(self):
        '''After an update to the linear weights, the sigmoidal weights must be
            must be calculated with a call to this function. 
            
            Sigmoidal weights represent the synaptic strength which cannot grow
            purely linearly since the maximum and minimum possible weight is
            bounded by physical constraints.
        '''
        mask1 = self.linMatrix <= 0
        self.matrix[mask1] = 0

        mask2 = self.linMatrix >= 1
        self.matrix[mask2] = 1

        mask3 = np.logical_not(np.logical_or(mask1, mask2))
        self.matrix[mask3] = self.sigmoid(self.linMatrix[mask3])

    def sigmoid(self, data):
        return 1 / (1 + np.power(self.Off*(1-data)/data, self.Gain))
    
    def InvSigMatrix(self):
        '''This function is only called when the weights are set manually to
            ensure that the linear weights (linMatrix) are accurately tracked.
        '''
        mask1 = self.matrix <= 0
        self.matrix[mask1] = 0

        mask2 = self.matrix >= 1
        self.matrix[mask2] = 1

        mask3 = np.logical_not(np.logical_or(mask1, mask2))
        self.linMatrix[mask3] = self.invSigmoid(self.matrix[mask3])
    
    def invSigmoid(self, data):
        return 1 / (1 + np.power((1/self.Off)*(1-data)/data, (1/self.Gain)))


    def __len__(self):
        return self.size

    def __str__(self):
        return f"\n\t\t{self.name.upper()} ({self.size} <={self.inLayer.name}) = {self.get()}"

class TransposeMesh(Mesh):
    '''A class for feedback meshes based on the transpose of another mesh.
    '''
    def __init__(self, mesh: Mesh,
                 inLayer: Layer,
                 AbsScale: float = 1,
                 RelScale: float = 0.2,
                 **kwargs) -> None:
        super().__init__(mesh.size, inLayer, AbsScale, RelScale, **kwargs)
        self.name = "TRANSPOSE_" + mesh.name
        self.mesh = mesh

        # self.fbScale = fbScale

        self.trainable = False

    def set(self):
        raise Exception("Feedback mesh has no 'set' method.")

    def get(self):
        # sndActAvgP = np.mean(self.inLayer.phaseHist["plus"])
        # self.setGscale()
        return self.mesh.Gscale * self.mesh.get().T 
    
    def getInput(self):
        return self.mesh.inLayer.getActivity()

    def Update(self, delta):
        return None
    
    
# class InhibMesh(Mesh):
#     '''A class for inhibitory feedback mashes based on fffb mechanism.
#         Calculates inhibitory input to a layer based on a mixture of its
#         existing activation and current input.
#     '''
#     FF = 1
#     FB = 1
#     FBTau = 1/1.4
#     FF0 = 0.1
#     Gi = 1.8

#     def __init__(self, ffmesh: Mesh, inLayer: Layer) -> None:
#         self.name = "FFFB_" + ffmesh.name
#         self.ffmesh = ffmesh
#         self.size = len(inLayer)
#         self.inLayer = inLayer
#         self.fb = 0
#         self.inhib = np.zeros(self.size)

#         self.trainable = False

#     def apply(self):
#         # guarantee that data can be multiplied by the mesh
#         ffAct = self.ffmesh.apply()[:len(self)]
#         ffAct = np.pad(ffAct, (0, self.size - len(ffAct)))
#         ffAct = np.maximum(ffAct-InhibMesh.FF0,0)

#         self.fb += InhibMesh.FBTau * (np.mean(self.inLayer.outAct) - self.fb)

#         self.inhib[:] = InhibMesh.FF * ffAct + InhibMesh.FB * self.fb
#         return InhibMesh.Gi * self.inhib

#     def set(self):
#         raise Exception("InhibMesh has no 'set' method.")

#     def get(self):
#         return self.apply()
    
#     def getInput(self):
#         return self.mesh.inLayer.outAct

#     def Update(self, delta):
#         return None

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


    def Update(self):
        super().Update()
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
        # TODO: update this code
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
    
