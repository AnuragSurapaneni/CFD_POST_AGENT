"""Example custom function for physical inputs defined in a request's constants."""

from cfdpost.custom import kolmogorov_scales


def calculate(dataset, constants):
    """Return global Kolmogorov scales from nu [m^2/s] and epsilon [m^2/s^3]."""
    nu = constants["kinematic_viscosity"]["value"]
    epsilon = constants["dissipation_rate"]["value"]
    return {"global": kolmogorov_scales(float(nu), float(epsilon)), "reduction": "identical"}
