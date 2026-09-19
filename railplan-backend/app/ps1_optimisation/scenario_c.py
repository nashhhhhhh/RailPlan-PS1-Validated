"""Scenario C entry point over the shared elastic-access CP-SAT core."""
from .scenario_b import solve as solve_elastic

def solve(dataset,data,options):
    return solve_elastic(dataset,data,options,'C')
