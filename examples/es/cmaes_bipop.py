#    This file is part of DEAP.
#
#    DEAP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    DEAP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with DEAP. If not, see <http://www.gnu.org/licenses/>.

"""Implementation of the BI-Population CMA-ES algorithm. As presented in
*Hansen, 2009, Benchmarking a BI-Population CMA-ES on the BBOB-2009 Function
Testbed* with the exception of the modifications to the original CMA-ES
parameters mentionned at the end of section 2's first paragraph.
"""

import numpy

from deap import algorithms
from deap import base
from deap import benchmarks
from deap import cma
from deap import creator
from deap import tools

# Problem size
N = 30

creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
creator.create("Individual", list, fitness=creator.FitnessMin)

def main(verbose=True):
    NRESTARTS = 10  # Initialization + 9 I-POP restarts
    SIGMA0 = 2.0    # 1/5th of the domain [-5 5]

    toolbox = base.Toolbox()
    toolbox.register("evaluate", benchmarks.rastrigin)

    halloffame = tools.HallOfFame(1)

    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", tools.mean)
    stats.register("std", tools.std)
    stats.register("min", min)
    stats.register("max", max)

    if verbose:
        column_names = ["gen", "evals", "restart", "regime"] + stats.functions.keys()
        logger = tools.EvolutionLogger(column_names)
        logger.logHeader()

    nsmallpopruns = 0
    smallbudget = list()
    largebudget = list()
    lambda0 = 4 + int(3 * numpy.log(N))
    regime = 1
    i = 0

    while i < (NRESTARTS + nsmallpopruns):
        # The first regime is enforced on the first and last restart
        # The second regime is run if its allocated budget is smaller than the allocated
        # large population regime budget
        if i > 0 and i < (NRESTARTS + nsmallpopruns) - 1 and sum(smallbudget) < sum(largebudget):
            lambda_ = int(lambda0 * (0.5 * (2**(i - nsmallpopruns) * lambda0) / lambda0)**(numpy.random.rand()**2))
            sigma = 2 * 10**(-2 * numpy.random.rand())
            nsmallpopruns += 1
            regime = 2
            smallbudget += [0]
        else:
            lambda_ = 2**(i - nsmallpopruns) * lambda0
            sigma = SIGMA0
            regime = 1
            largebudget += [0]
        
        t = 0
        
        # Set the termination criterion constants
        if regime == 1:
            MAXITER = 100 + 50 * (N + 3)**2 / numpy.sqrt(lambda_)
        elif regime == 2:
            MAXITER = 0.5 * largebudget[-1] / lambda_
        TOLHISTFUN = 10**-12
        TOLHISTFUN_ITER = 10 + int(numpy.ceil(30. * N / lambda_))
        EQUALFUNVALS = 1. / 3.
        EQUALFUNVALS_K = int(numpy.ceil(0.1 + lambda_ / 4.))
        TOLX = 10**-12
        TOLUPSIGMA = 10**20
        CONDITIONCOV = 10**14
        STAGNATION_ITER = int(numpy.ceil(0.2 * t + 120 + 30. * N / lambda_))
        NOEFFECTAXIS_INDEX = t % N

        equalfunvalues = list()
        bestvalues = list()
        medianvalues = list()

        # We start with a centroid in [-4, 4]**D, and a sigma of 2 (1/5 of the domain)
        strategy = cma.Strategy(centroid=numpy.random.uniform(-4, 4, N), sigma=sigma, lambda_=lambda_)
        toolbox.register("generate", strategy.generate, creator.Individual)
        toolbox.register("update", strategy.update)

        # Run the current regime until one of the following is true:
        ## Note that the algorithm won't stop by itself on the optimum (0.0 on rastrigin).
        while (# The maximum number of iteration per CMA-ES ran
               t < MAXITER and 
               # The range of the best values is smaller than the threshold
               (max(stats.min[i][-TOLHISTFUN_ITER:])[0] - min(stats.min[i][-TOLHISTFUN_ITER:])[0] > TOLHISTFUN
                ## At the first iteration, there is no stats.min[i]
                if (len(stats.min) > i and not len(stats.min[i]) < TOLHISTFUN_ITER) else True) and
               # In 1/3rd of the last N iterations the best and k'th best solutions are equal
               (sum(equalfunvalues[-N:]) / float(N) < EQUALFUNVALS if t > N else True) and
               # All components of pc and sqrt(diag(C)) are smaller than the threshold
               (any(strategy.pc > TOLX) or any(numpy.sqrt(numpy.diag(strategy.C)) > TOLX)) and
               # The sigma ratio is bigger than a threshold
               strategy.sigma / SIGMA0 < strategy.diagD[-1]**2 * TOLUPSIGMA and
               # Stagnation occured
               ((numpy.median(bestvalues[-20:]) < numpy.median(bestvalues[-STAGNATION_ITER:-STAGNATION_ITER + 20]) or
                 numpy.median(medianvalues[-20:]) < numpy.median(medianvalues[-STAGNATION_ITER:-STAGNATION_ITER + 20]))
                if (len(bestvalues) > STAGNATION_ITER and len(medianvalues) > STAGNATION_ITER) else True) and
               # The condition number is bigger than a threshold
               strategy.cond < 10**14 and
               # The coordinate axis std is too low
               any(strategy.centroid != strategy.centroid + 0.1 * strategy.sigma * strategy.diagD[-NOEFFECTAXIS_INDEX] * strategy.B[-NOEFFECTAXIS_INDEX]) and
               # The main axis std has no effect
               all(strategy.centroid != strategy.centroid + 0.2 * strategy.sigma * numpy.diag(strategy.C))):
            
            # Generate a new population
            population = toolbox.generate()
            # Evaluate the individuals
            fitnesses = toolbox.map(toolbox.evaluate, population)
            for ind, fit in zip(population, fitnesses):
                ind.fitness.values = fit
            
            halloffame.update(population)
            stats.update(population, index=i, add=True)

            # Update the strategy with the evaluated individuals
            toolbox.update(population)

            if verbose:
                logger.logGeneration(gen=t, evals=lambda_, restart=i, regime=regime, stats=stats, index=i)
                
            # Count the number of times the k'th best solution is equal to the best solution
            # At this point the population is sorted (method update)
            if population[-1].fitness == population[-EQUALFUNVALS_K].fitness:
                equalfunvalues.append(1)
            
            # Log the best and median value of this population
            bestvalues.append(population[-1].fitness.values)
            medianvalues.append(population[len(population)/2].fitness.values)

            # First run does not count into the budget
            if regime == 1 and i > 0:
                largebudget[-1] += lambda_
            elif regime == 2:
                smallbudget[-1] += lambda_

            t += 1
            STAGNATION_ITER = int(numpy.ceil(0.2 * t + 120 + 30. * N / lambda_))
            NOEFFECTAXIS_INDEX = t % N

        i += 1

    return halloffame[0]

if __name__ == "__main__":
    main()