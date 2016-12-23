"""
pynpuzzle - Solve n-puzzle with Python

Iterative deepening depth-first search algorithm

Version : 1.0.0
Author : Hamidreza Mahdavipanah
Repository: http://github.com/mahdavipanah/pynpuzzle
License : MIT License
"""
from .util.tree_search import Node


def search(state, goal_state):
    """Iterative deepening depth-first"""
    depth = 0

    def dls(node):
        if node.is_goal(goal_state):
            return node
        if node.depth < depth:
            node.expand()
            for child in node.children:
                result = dls(child)
                if result:
                    return result
        return None

    answer = None
    while not answer:
        answer = dls(Node(state))
        depth += 1

    output = []
    output.append(answer.state)
    for parent in answer.parents():
        output.append(parent.state)
    output.reverse()

    return output
