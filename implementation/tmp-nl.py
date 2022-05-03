from math import sqrt, asin, pi
import numpy as np
from itertools import product
import collections
from gurobipy import *
from decimal import Context


# inputs (x,y) domain and outputs (a,b) domain
domain_xy = [0, 1]
domain_ab = [-1, 1]

# dictionnary giving the basis order, i.e p[(a,b,x,y)] = index of p(ab|xy) in the basis order chosen
indexes_p = collections.defaultdict(int)
i = 0
for x, y in product(domain_xy, repeat=2):
    for a, b in product(domain_ab, repeat=2):
        indexes_p[a, b, x, y] = i
        i += 1


def vec_d_lambda(l):
    dl = []
    for x, y in product(domain_xy, repeat=2):
        for a, b in product(domain_ab, repeat=2):
            dl.append(int(l[x] == a and l[y + 2] == b))
    return dl


def ls_quantum_p():
    """
    Quantum probability distribution,
    computed by solving the system of equations.
    """
    # Constraint Coefficients
    A = np.zeros([16, 16])
    # Left Side
    B = np.zeros([16])
    i = 0

    # <ψ| A_x x B_y |ψ> = xy/sqrt(2)
    for x, y in product(domain_xy, repeat=2):
        for a, b in product(domain_ab, repeat=2):
            A[i, indexes_p[a, b, x, y]] = a * b
        B[i] = (-1) ** (x * y) / sqrt(2)
        i += 1

    # <ψ| A_x x B_y |ψ> = 1
    for x, y in product(domain_xy, repeat=2):
        for a, b in product(domain_ab, repeat=2):
            A[i, indexes_p[a, b, x, y]] = 1
        B[i] = 1
        i += 1

    # <ψ| A_x x 1_B |ψ> = 0
    for x, y in product(domain_xy, repeat=2):
        for a, b in product(domain_ab, repeat=2):
            A[i, indexes_p[a, b, x, y]] = a
        B[i] = 0
        i += 1

    # <ψ| 1_A x B_y |ψ> = 0
    for x, y in product(domain_xy, repeat=2):
        for a, b in product(domain_ab, repeat=2):
            A[i, indexes_p[a, b, x, y]] = b
        B[i] = 0
        i += 1

    # Solve linear system Ax = B
    return list(np.linalg.solve(A, B))


# Lambdas are the possible outputs assignement (a0,a1,b0,b1), there are 16 possible lambdas
lambdas = []
for a0, a1 in product(domain_ab, repeat=2):
    for b0, b1 in product(domain_ab, repeat=2):
        lambdas.append((a0, a1, b0, b1))

# D_l is a matrix with each row corresponding to a deterministic behavior lambda
D_l = [np.array(vec_d_lambda(l)) for l in lambdas]

# M is the transpose of D_l , one column = one deterministic behavior d_lambda
M = np.column_stack(D_l)


use_qp_mask = [  # 0 and 4 to Tru gives a quantum behavior
    True,
    False,
    False,
    False,
    True,
    False,
    False,
    False,
    True,
    False,
    False,
    False,
    True,
    False,
    False,
    False,
]

quantum_p = ls_quantum_p()


# define the model
m = Model()
m.Params.LogToConsole = 0
m.params.NonConvex = 2  # Needed since the model is non convex.


# mu_lambda is a vector of the coeff of the linear combination of the vectors d_lambda
mu_lambda = [m.addVar(name=f"mu_{i}", vtype="C") for i in range(len(lambdas))]

P = [m.addVar(name=f"p_{i}", vtype="C") for i in range(16)]
# P_l : vector  of the convex combination of the deterministic points,
# i.e P_l = sum(mu_lambda * vec_d_lambda) where the sum is on the lambdas
P_l = np.dot(M, mu_lambda)

# add a variable Q (visibility)
Q = m.addVar(name="Q", vtype="C")

# update the model with the newly defined variables
m.update()

# Add the constraints
for i in range(len(P)):
    m.addConstr(((1 - Q) * P[i] + Q - P_l[i] == 0))

# Constraints on probabilities
m.addConstr(quicksum(mu_lambda[i] for i in range(len(lambdas))) >= 1)

for i in range(len(lambdas)):
    m.addConstr(mu_lambda[i] >= 0)
    # if not use_qp_mask[i]:  # Add the constraint only if it's a variable
    m.addConstr(P[i] >= 0)

# Define a constraint for the chsh inequality
chsh = LinExpr()

E = []

for x, y in product(domain_xy, repeat=2):
    e = LinExpr()  # represents an expecation value <Ax By>
    for a, b in product(domain_ab, repeat=2):
        e += a * b * P[indexes_p[a, b, x, y]]
    # Constraints from (10) p.6 : Bell nonlocality
    m.addConstr(e <= 1)
    m.addConstr(e >= -1)
    E.append(e)
    chsh += (-1) ** (x * y) * e


for x, y in product(domain_xy, repeat=2):
    # Each marginal must sum up to one
    m.addConstr(
        quicksum(P[indexes_p[a, b, x, y]] for a, b in product(domain_ab, repeat=2)) == 1
    )
# If useless, removed by guroby
m.addConstr(quicksum(P[i] for i in range(len(lambdas))) == 4)

for x, y in product(domain_xy, repeat=2):
    m.addConstr(
        quicksum(a * P[indexes_p[a, b, x, y]] for a, b in product(domain_ab, repeat=2))
        == 0
    )

for x, y in product(domain_xy, repeat=2):
    m.addConstr(
        quicksum(b * P[indexes_p[a, b, x, y]] for a, b in product(domain_ab, repeat=2))
        == 0
    )

# for i in range(16):
# if use_qp_mask[i]:
#     m.addConstr(P[i] == quantum_p[i])


m.addConstr(Q >= 0)
m.addConstr(Q <= 1)


run = True
d = 10e-5
upper_bound = 0
previous_chsh_value = 0
n_iter = 0
E = []


c = Context(prec=15)

while run:
    # bound = m.addConstr(chsh >= 2 * sqrt(2) - upper_bound)
    # bound = m.addConstr(chsh <= 1 + upper_bound)
    bound = m.addConstr(chsh <= 2 * sqrt(2))
    m.update()

    m.setObjective(chsh, GRB.MAXIMIZE)

    m.update()
    m.optimize()
    E = []
    chsh_check = 0
    for x, y in product(domain_xy, repeat=2):
        e = 0
        for a, b in product(domain_ab, repeat=2):
            e += a * b * P[indexes_p[a, b, x, y]].X
        if e >= 0.99:
            e = 1
        E.append(e)
        chsh_check += ((-1) ** (x * y)) * asin((e))
    # print(chsh_check, chsh.getValue())
    run = (
        chsh_check <= pi
        and
        # asserts the behavior is local
        chsh.getValue() != previous_chsh_value
        and chsh.getValue() <= 2 * sqrt(2)
        # and n_iter < 3
    )
    print(
        f"check : {c.create_decimal(abs(chsh_check))} CHSH value : {c.create_decimal(chsh.getValue())}            ",
        end="\r",
    )
    previous_chsh_value = chsh.getValue()
    upper_bound += d
    n_iter += 1
    m.remove(bound)


print(f"Reached stop condition in {n_iter} iterations:               ")
print(f"Objective = {previous_chsh_value} - Check = {chsh_check}")
print(f"{Q.X = }")
print(f"Computed probability distribution : \n{([P[i].X for i in range(16)])}")
print(f"CHSH value : {chsh.getValue()}")
print(f"{E = }")
