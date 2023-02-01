import copy


import sys, os
sys.path.insert(0, os.path.join(sys.path[0],'../src'))

from vivilux import *


# from ..src.vivilux import activations, __init__, learningRules, metrics, photonics
from vivilux.learningRules import CHL, GeneRec
from vivilux.metrics import RMSE
import numpy as np
import matplotlib.pyplot as plt
np.random.seed(seed=0)

numSamples = 40

def CHL_trans(inLayer, outLayer):
    return CHL(inLayer, outLayer).T

#define input and output data (must be normalized and positive-valued)
vecs = np.random.normal(size=(numSamples, 4))
mags = np.linalg.norm(vecs, axis=-1)
# print(mags,mags[...,np.newaxis])
inputs = np.abs(vecs/mags[...,np.newaxis])
vecs = np.random.normal(size=(numSamples, 4))
mags = np.linalg.norm(vecs, axis=-1)
targets = np.abs(vecs/mags[...,np.newaxis])
del vecs, mags

# netGR = FFFB([
#     Layer(4, learningRule=GeneRec),
#     Layer(4, learningRule=GeneRec)
# ], Mesh, learningRate = 0.1)

netGR = FFFB([
    Layer(4, learningRule=GeneRec),
    Layer(4, learningRule=GeneRec),
    Layer(4, learningRule=GeneRec)
], Mesh, learningRate = 0.1)

# print(type(mahmoudnetGR.layers))

netCHL = copy.deepcopy(netGR)
netCHL.setLearningRule(CHL)

netCHL_T = copy.deepcopy(netGR)
netCHL_T.setLearningRule(CHL_trans)

def trainingLoopCHL(W1, W2, inputs, targets, numEpochs=100, numSamples=40,
                    numTimeSteps=100, phaseStep = 50, learningRate = 0.1,
                    deltaTime = 0.1):
    '''CHL:
        Training using Contrastive Hebbian Learning rule
    '''
    #Allocate error traces
    fullErrorTrace = np.zeros(numTimeSteps*numSamples*numEpochs)
    errorTrace = np.zeros(numEpochs)
    
    #allocate space for variables during learning
    print("Allocating space for loop variables...")
    matrixDimension = len(W1)
    linInp = np.zeros(matrixDimension) #linear input layer
    actInp = np.zeros(matrixDimension)
    linOut = np.zeros(matrixDimension)
    actOut = np.zeros(matrixDimension)
    minusPhaseIn = np.zeros(matrixDimension)
    minusPhaseOut = np.zeros(matrixDimension)
    minusPhaseIn = np.zeros(matrixDimension)
    minusPhaseOut = np.zeros(matrixDimension)
    weightIn = W1.copy()
    weightOut = W2.copy()
    print("Beginning training...")
    # print(">> pre-training: weightIn = ", weightIn, "pre-training: weightOut = ", weightOut)

    for epoch in range(numEpochs):
        epochErrors = np.zeros(numSamples)
        # epoch_predictions = np.zeros((numSamples, 4))
        for sample in range(numSamples): #>1
            currentInput = inputs[sample]
            targetOutput = targets[sample]
            #>2

            for timeStep in range(numTimeSteps):#>3: start predict
                # if epoch == 0 and sample == 0:
                #     print("fun>time step ",timeStep ," inference of the first data sample: ", actInp)
                #update activation values
                linInp += deltaTime*(np.abs(weightIn @ currentInput)**2
                                   + np.abs(weightOut.T @ actOut)**2
                                   - linInp)
                actInp = Sigmoid(linInp)
                if timeStep <= phaseStep:
                    linOut += deltaTime*(np.abs(weightOut @ actInp)**2-linOut)
                    actOut = Sigmoid(linOut) # the result of inference
                    if timeStep == phaseStep:
                        minusPhaseIn = actInp
                        minusPhaseOut = actOut
                        # epochErrors[sample] = RMSE(targetOutput, actOut)
                        # epoch_predictions[sample] = actOut
                        # if epoch == 0:
                        #     print("fun>at sample ",sample ," inference of the first data sample: ", actOut, " (should be close to ", targetOutput,")")
                        epochErrors[sample] = np.sum((targetOutput - actOut)**2)
                #>4: end predict
                else:#>5: start observe
                    actOut = targetOutput
                #>6: end observe
            
                
                #Record traces
                traceIndex = epoch*(numSamples*numTimeSteps)+sample*numTimeSteps + timeStep
                # inputTrace[traceIndex] = actInp
                # outputTrace[traceIndex] = actOut
                # weightInTrace[traceIndex] = weightIn.flatten()
                # weightOutTrace[traceIndex] = np.abs(weightOut).flatten()
                fullErrorTrace[traceIndex] = np.sqrt(np.sum((targetOutput - actOut)**2))
            
            plusPhaseIn = actInp
            plusPhaseOut = actOut
            # mahmoud: I couldn't see how the none-training in the zeroth epoch is implemented in the net class.
            if epoch != 0: # don't train on first epoch to establish RMSE
                #Contrastive Hebbian Learning rule
                ####(equivalent to GenRec with symmetry and midpoint approx)
                ######## (generally converges faster)
                # deltaWeightIn = (plusPhaseIn[:,np.newaxis] @ plusPhaseOut[np.newaxis,:] -
                #                 minusPhaseIn[:,np.newaxis] @ minusPhaseOut[np.newaxis,:])
                # #Mahmoud
                # deltaWeightIn = (plusPhaseIn[:,np.newaxis] @ plusPhaseOut[np.newaxis,:] -
                #                 minusPhaseIn[:,np.newaxis] @ minusPhaseOut[np.newaxis,:])
                # #end mahmoud
                # weightIn += learningRate * deltaWeightIn # FIXME FREEZE FIRST LAYER
                # print("---------\n",plusPhaseOut, minusPhaseOut,minusPhaseIn,"\n---------\n")
                deltaWeightOut = (plusPhaseOut - minusPhaseOut)[:,np.newaxis] @ minusPhaseIn[np.newaxis,:]

                # Mahmoud: if three layers, which weights to update?
                weightOut += learningRate * deltaWeightOut
        # print(">> for epoch=",epoch," weightIn = ", weightIn, "post-training: weightOut = ", weightOut)
        
        #Store RMSE for the given epoch
        errorTrace[epoch] = np.sqrt(np.mean(epochErrors))
        # errorTrace[epoch] = RMSE(targets, epoch_predictions)

    # print(">> post-training: weightIn = ", weightIn, "post-training: weightOut = ", weightOut)
    print("Done")


    # print("final input weight matrix:\n", weightIn)
    # print("final output weight matrix:\n", weightOut)
    print(f"initial RMSE: {errorTrace[0]}, final RMSE: {errorTrace[-1]}")
    print(f"Training occured?: {errorTrace[0] > errorTrace[-1]}")

    return errorTrace

########## old
print("Old GR")

netGR_basic_method = copy.deepcopy(netGR)
weights = netGR_basic_method.getWeights()
# print("w0",weights[0], "w1",weights[1])
# print(inputs, targets)
oldResult = trainingLoopCHL(weights[0], weights[1],inputs, targets, numEpochs=50, learningRate=0.1)
plt.plot(oldResult, label="Old GR")
########### end
print("GeneRec")
# print(netGR)
resultGR = netGR.Learn(inputs, targets, numEpochs=50)
print(resultGR)
plt.plot(resultGR, label="GeneRec")

# print("CHL")
# print(netCHL)
# resultCHL = netCHL.Learn(inputs, targets, numEpochs=200)
# plt.plot(resultCHL, label="CHL")

# print("CHL_T")
# print(netCHL_T)
# resultCHL_T = netCHL_T.Learn(inputs, targets, numEpochs=200)
# plt.plot(resultCHL_T, label="CHL_T")


plt.title("Iris Dataset")
plt.ylabel("RMSE")
plt.xlabel("Epoch")
plt.legend()
plt.show()