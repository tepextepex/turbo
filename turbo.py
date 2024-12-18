"""
Bulk aerodynamic technique for estimating heat exchange in turbulent flow.
Uses different parametrization for stable and unstable atmospheric conditions.


See references:
1) Munro, D.S. 1989. Surface roughness and bulk heat transfer on a
glacier: comparison with eddy correlation. J. Glaciol., 35(121),
343–348.
2) Munro, D.S. 1990. Comparison of melt energy computations and
ablatometer measurements on melting ice and snow. Arct. Alp.
Res., 22(2), 153–162.
3) Beljaars, A. and A. Holtslag. 1991. Flux parameterization over land
surface for atmospheric models. J. Appl. Meteorol., 30(3),
327–341.
4) Hock, R., & Holmgren, B. (2005). A distributed surface energy-balance model
for complex topography and its application to Storglaciären, Sweden.
Journal of Glaciology, 51(172), 25-36. doi:10.3189/172756505781829566
5) Wheler, B., & Flowers, G. (2011). Glacier subsurface heat-flux characterizations for energy-balance modelling
in the Donjek Range, southwest Yukon, Canada. Journal of Glaciology, 57(201), 121-133. doi:10.3189/002214311795306709
"""
import traceback

import numpy as np
from math import pi
from timeit import timeit

# np.seterr(all='raise')

CONST = {
    "specific_gas_constant": 287.058,  # [J kg-1 K-1]
    "k": 0.4,  # von Karman constant [dimensionless]
    "g": 9.81,  # acceleration due to the gravity [m s-2]
    "specific_heat_capacity": 1010,  # ...of an air [J kg-1 K-1]
    "Ts": 0 + 273.15,  # the absolute temperature of melting ice/snow surface [K]
    "es": 611,  # water vapour pressure at the melting ice/snow surface [Pa]
    "latent_heat_vaporization": 2.514 * 10 ** 6,  # latent heat of water vaporization [J kg-1]
    "latent_heat_sublimation": 2.849 * 10 ** 6,  # latent heat of water ice sublimation [J kg-1]
    "zm": 0.001  # empirical roughness length for momentum (for wind) over the ice/snow surface [m]
}

#@timeit
def calc_turbulent_fluxes(z, uz, Tz, P, rel_humidity, surface_temp=None, L=None, zm=None, z_h_or_e=None,
                          max_iter=5, andreas=False, verbose=False):
    """
    Computes turbulent heat fluxes based on the bulk aerodynamic method.
    Monin-Obukhov stability length L, if unknown,  is defined from iterative process with initial assumption of z/L=0
    Turbulent processes parametrization for stable atmosphere follows Beljaars and Holtslag (1991)

    :param z: height of measurements above the surface, usually 2m [m]
    :param uz: wind speed at the height of z [m s-1]
    :param Tz: absolute air temperature at the height of z [K]
    :param P: air pressure at the height of z [Pa]
    :param rel_humidity: relative humidity of the air at the height of z [from 0.0 to 1.0]
    :param surface_temp: if None, assumed to be constant, equalling 273.15 K (as a melting surface)
    :param L: Monin-Obukhov stability length [m]
    :param zm: roughness length for momentum [m]
    :param zm: z_h_or_e: roughness length for water vapour [m]
    :param max_iter: maximum number of iterations to define Monin-Obukhov stability length [int]
    :param verbose: shows result of every iteration [True/False]
    :return: a tuple (sensible_heat_flux, latent_heat_flux, monin_obukhov_length) in [W m-2] and [m]
    """
    try:
        if L is None:
            sensible_flux, monin_obukhov_length = _calc_sensible_iteratively(z, uz, Tz, P, surface_temp,
                                                                             zm=zm, z_h_or_e=z_h_or_e,
                                                                             andreas=andreas,
                                                                             max_iter=max_iter, verbose=verbose)
        else:
            monin_obukhov_length = L
            sensible_flux = _calc_sensible(z, uz, Tz, P, Ts=surface_temp, L=monin_obukhov_length,
                                           zm=zm, z_h_or_e=z_h_or_e, andreas=andreas)

        latent_flux = _calc_latent(z, uz, Tz, P, rel_humidity, Ts=surface_temp, L=monin_obukhov_length,
                                   zm=zm, z_h_or_e=z_h_or_e, andreas=andreas)

        return sensible_flux, latent_flux, monin_obukhov_length

    except:
        print(traceback.print_exc())


def _get_dry_air_density(t_air, p_air):
    specific_gas_constant = CONST["specific_gas_constant"]
    return p_air / (specific_gas_constant * t_air)


def _calc_sensible_iteratively(z, uz, Tz, P, Ts, zm=None, z_h_or_e=None,
                               max_iter=5, andreas=False, verbose=False):
    if isinstance(max_iter, int) and max_iter < 10:
        max_iter = max_iter
    else:
        max_iter = 5  # 5 iterations ought to be enough for anybody (usually less)

    # calculation of L requires knowledge of both Qh and the friction velocity u_aster:
    # we need to make an initial guess of L,
    # assuming that z/L = 0 by passing L=None into the following functions:
    u_aster = _calc_friction_velocity(uz, z, zm=zm, L=None)
    Qh = _calc_sensible(z, uz, Tz, P, Ts=Ts, zm=zm, z_h_or_e=z_h_or_e, andreas=andreas, L=None)
    L = _calc_monin_obukhov_length(Tz, P, u_aster, Qh)

    if verbose:
        print("Initial guess:")
        print("u*=%.3f m/s" % u_aster)
        print("Qh=%.1f W/m^2" % Qh)
        print("Monin-Obukhov length is %.1f m" % L)

    for i in range(0, max_iter):
        u_aster = _calc_friction_velocity(uz, z, zm=zm, L=L)
        Qh = _calc_sensible(z, uz, Tz, P, Ts, zm=zm, z_h_or_e=z_h_or_e, andreas=andreas, L=L)
        L = _calc_monin_obukhov_length(Tz, P, u_aster, Qh)
        if verbose:
            print("***************************")
            print("Iteration %d" % (i + 1))
            print("u*=%.3f m/s" % u_aster)
            print("Qh=%.1f W/m^2" % Qh)
            print("Monin-Obukhov length is %.1f m" % L)

    return Qh, L


def _calc_monin_obukhov_length(Tz, P, u_aster, Qh):
    """
    Computes Monin-Obukhov stability length [m]
    :param Tz: absolute air temperature at the height "z" above the surface [K]
    :param P: air pressure at the height "z" [Pa]
    :param u_aster: friction velocity [m s-1]
    :param Qh: sensible heat flux [W m-2]
    :return: Monin-Obukhov length [m]
    """
    k = CONST["k"]
    g = CONST["g"]
    Cp = CONST["specific_heat_capacity"]
    rho = _get_dry_air_density(Tz, P)  # kg m-3, air density
    num = rho * Cp * u_aster ** 3 * Tz
    denum = k * g * Qh
    return num / denum


def _calc_sensible(z, uz, Tz, P, Ts=None, zm=None, z_h_or_e=None, L=None, andreas=False):
    """
    Computes sensible heat flux [W m-2]
    :param z:
    :param uz:
    :param Tz:
    :param P:
    :param L:
    :return:
    """
    if Ts is None:
        Ts = CONST["Ts"]  # the absolute temperature of melting ice/snow surface [K]
    Cp = CONST["specific_heat_capacity"]
    rho = _get_dry_air_density(Tz, P)  # kg m-3, air density
    CH = _calc_turb_exchange_coef(z, zm=zm, z_h_or_e=z_h_or_e, L=L, andreas=andreas, uz=uz)

    return CH * Cp * rho * uz * (Tz - Ts)


def _calc_latent(z, uz, Tz, P, rel_humidity, Ts=None, zm=None, z_h_or_e=None, L=None, andreas=False):
    """
    Computes latent heat flux [W m-2]
    :param z:
    :param uz:
    :param Tz:
    :param P:
    :param rel_humidity:
    :param L:
    :return:
    """
    if Ts is None:
        es = CONST["es"]  # Pa, water vapour pressure at the ice surface
    else:
        es = _calc_e_max(Ts, P)
    Lv = CONST["latent_heat_vaporization"]  # J kg-1, latent heat of vaporization (for positive surface temps)
    Ls = CONST["latent_heat_sublimation"]  # J kg-1, latent heat of sublimation (for negative surface temps)

    e_max = _calc_e_max(Tz, P)  # Pa, partial water vapor pressure for saturated air
    ez = e_max * rel_humidity  # Pa, partial vapour pressure at the height of measurements "z"
    rho = _get_dry_air_density(Tz, P)  # kg m-3, air density
    CE = _calc_turb_exchange_coef(z, zm=zm, z_h_or_e=z_h_or_e, L=L, andreas=andreas, uz=uz)

    flux = CE * rho * uz * 0.622 / P * (ez - es)

    if Ts is None:
        # since we assume surface temperature is at melting point, sublimation never happens:
        flux = flux * Lv
    else:
        # else we should look into surface temp array
        # and handle numpy arrays and float inputs a little bit differently:
        if type(flux) == np.ndarray:
            flux = np.where(Ts >= 0, flux * Lv, flux * Ls)
        # you'll get "RuntimeWarning: invalid value encountered in greater" dut to np.nan values - never mind
        else:
            flux = flux * Lv if Ts >= 0 else flux * Ls

    return flux


def get_andreas_bi(Re):
    if isinstance(Re, np.ndarray):
        b_0 = np.full(Re.shape, 1.25)
        b_1 = np.full(Re.shape, 0.00)
        b_2 = np.full(Re.shape, 0.00)

        b_0 = np.where(Re > 0.135, 0.149, b_0)
        b_1 = np.where(Re > 0.135, -0.55, b_1)
        b_2 = np.where(Re > 0.135, 0.0, b_2)

        b_0 = np.where(Re > 2.5, 0.317, b_0)
        b_1 = np.where(Re > 2.5, -0.565, b_1)
        b_2 = np.where(Re > 2.5, -0.183, b_2)
    else:
        if Re <= 0.135:
            b_0 = 1.25
            b_1 = 0
            b_2 = 0
        elif Re <= 2.5:
            b_0 = 0.149
            b_1 = -0.55
            b_2 = 0
        else:
            b_0 = 0.317
            b_1 = -0.565
            b_2 = -0.183
    return b_0, b_1, b_2


def calc_andreas_z0(uz, z, zm, L):
    """
    Computation of the non-constant z_0_h or z_0_e depending on the Reynolds number.
    Source: Andreas, E. L. (1987). A theory for the scalar roughness and the scalar transfer coefficients over snow
    and sea ice. Boundary-Layer Meteorology, 38(1–2), 159–184. https://doi.org/10.1007/BF00121562
    :param uz:
    :param z:
    :param zm:
    :param L:
    :return:
    """
    u_aster = _calc_friction_velocity(uz, z, zm=zm, L=L)
    nu = 1.5e-5  # [m2 s-1] kinematic viscosity coefficient for the air
    Re = u_aster * zm / nu

    b_0, b_1, b_2 = get_andreas_bi(Re)
    # DEBUG:
    # if np.any(Re < 0):
    #     # if np.nanmean(uz) <= 0.1:
    #     # import matplotlib.pyplot as plt
    #     print(Re.shape)
    #     print(f"Re={round(Re, 3)}; U*={round(u_aster, 3)}")
    #     # print(f"uz={round(uz, 3)}; z={round(z, 3)}; z_0_m={zm}; L={round(L, 3)}")
    #     print(f"uz={round(uz, 3)}")
    #     print(f"z={round(z, 3)}")
    #     print(f"z_0_m={zm}")
    #     if L is not None:
    #         print(f"L={L}")
    #     # plt.imshow(Re)
    #     # plt.show()
    log_Re = np.log(Re)
    return zm * np.exp(b_0 + b_1 * log_Re + b_2 * log_Re ** 2)


def _calc_turb_exchange_coef(z, L=None, zm=None, z_h_or_e=None, andreas=False, uz=None):
    """
    Computes the turbulent exchange coefficients for sensible (CH) or for latent flux (CE)
    under stable atmospheric conditions
    :param z: height of measurements above the surface [m]
    :param L: Monin-Obukhov stability length [m]
    :return:
    """
    k = CONST["k"]  # dimensionless, von Karman constant
    if zm is None:
        zm = CONST["zm"]  # meters, roughness length for momentum
    if z_h_or_e is None:
        # z_h_or_e = zm / 100  # meters, roughness length for heat or water vapour
        z_h_or_e = zm / 10  # meters, let's try to increase it 10 times (according to eddie-covariance measurements of Aug 2022)
    if andreas:
        if uz is None:
            raise ValueError("You must specify Uz parameter to use 'andreas=True' option")
        else:
            z_h_or_e = calc_andreas_z0(uz, z, zm, L)
    num = k ** 2
    if L is not None:
        minus_psi_m = _calc_minus_psi_m(z, L)
        minus_psi_h_or_e = _calc_minus_psi_h_or_e(z, L)
        denum = (np.log(z / zm) + minus_psi_m * (z / L)) * (np.log(z / z_h_or_e) + minus_psi_h_or_e * (z / L))
    else:
        denum = np.log(z / zm) * np.log(z / z_h_or_e)
    return num / denum


def _calc_friction_velocity(uz, z, L=None, zm=None):
    k = CONST["k"]  # dimensionless, von Karman constant
    if zm is None:
        zm = CONST["zm"]  # meters, roughness length for momentum
    num = k * uz
    if L is not None:
        minus_psi_m = _calc_minus_psi_m(z, L)
        # denum = np.log(z / zm) + minus_psi_m * (z / L)  # this formula from Munro, 1990, has a typo! DO NOT USE
        denum = np.log(z / zm) + minus_psi_m  # and this equation produces strange results when Monin-Obukhov L is near-zero
        # denum = np.log(z / zm) + minus_psi_m - _calc_minus_psi_m(zm, L)  # Beljaars & Holtslag 1991, no negative velocities around L=0 TODO: Investigate
    else:
        denum = np.log(z / zm)
    return num / denum


def _calc_minus_psi_m(z, L):
    """
    Computes stability function Psi-M in integrated form
    :return:
    """
    a = 0.7
    b = 0.75
    c = 5
    d = 0.35

    zeta = z / L
    if isinstance(zeta, np.ndarray):
        psi_m = np.zeros(zeta.shape)
        x = _calc_Dyer_x(zeta)
        psi_m = np.where(zeta >= 0,
                         a * zeta + b * (zeta - c / d) * np.exp(-d * zeta) + b * c / d,
                         -(2 * np.log((1 + x) / 2) + np.log((1 + x ** 2) / 2) - 2 * np.arctan(x) + pi / 2))
        return psi_m
    else:
        if zeta >= 0:
            # under stable conditions:
            return a * zeta + b * (zeta - c / d) * np.exp(-d * zeta) + b * c / d
        else:
            # under unstable conditions:
            x = _calc_Dyer_x(zeta)
            return -(2 * np.log((1 + x) / 2) + np.log((1 + x ** 2) / 2) - 2 * np.arctan(x) + pi / 2)


def _calc_minus_psi_h_or_e(z, L):
    """
    Computes stability function Psi-H or Psi-E in integrated form
    :return:
    """
    a = 0.7
    b = 0.75
    c = 5
    d = 0.35

    zeta = z / L
    if isinstance(zeta, np.ndarray):
        psi = np.zeros(zeta.shape)
        x = _calc_Dyer_x(zeta)
        psi = np.where(zeta >= 0,
                       (1 + 2 * a * zeta / 3) ** 1.5 + b * (zeta - c / d) * np.exp(-d * zeta) + b * c / d - 1,
                       -(2 * np.log((1 + x ** 2) / 2)))
        return psi
    else:
        if zeta >= 0:
            # under stable conditions:
            return (1 + 2 * a * zeta / 3) ** 1.5 + b * (zeta - c / d) * np.exp(-d * zeta) + b * c / d - 1
        else:
            # under unstable conditions:
            x = _calc_Dyer_x(zeta)
            return -(2 * np.log((1 + x ** 2) / 2))


def _calc_Dyer_x(zeta):
    return (1 - 16 * zeta) ** (1 / 4)


def _calc_e_max(t_air, air_pressure):
    """
    Computes partial water vapour pressure of saturated (100%-moist) air [Pa, not hPa and not kPa!]
    :param t_air: in Kelvin
    :param air_pressure: in Pascals
    :return:
    """
    t_air = t_air - 273.15
    air_pressure = air_pressure / 100
    ew_t = 611.2 * np.exp((17.62 * t_air) / (243.12 + t_air))
    f_p = 1.0016 + 3.15 * 10 ** -6 * air_pressure - 0.074 / air_pressure
    return f_p * ew_t


if __name__ == "__main__":
    """ Usage example """
    z = 1.6  # m
    uz = 2.5  # m/s
    Tz = 3 + 273.15  # K
    # Tz = -10 + 273.15  # K
    P = 99000  # Pascals
    rel_humidity = 0.85
    roughness = 0.01  # (empirical) roughness length for momentum (for wind) [m]
    # T_surf = 273.15  # K
    T_surf = None
    ############################
    QH, QE, L = calc_turbulent_fluxes(z, uz, Tz, P, rel_humidity, T_surf, zm=roughness, max_iter=5, verbose=True)
    print("******************")
    print("FINAL RESULT:")
    print("Sensible heat flux is %.1f W m-2" % QH)
    print("Latent heat flux is %.1f W m-2" % QE)
    print("Monin-Obukhov stability length is %.1f m" % L)
############################
# print(_calc_e_max(273.15, P))
