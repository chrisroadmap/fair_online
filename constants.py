# -*- coding: utf-8 -*-

"""
FaIR web application constants
"""

# known / acceptable scenarios:
SCENARIOS = ['ssp119', 'ssp126', 'ssp245', 'ssp370', 'ssp585']
# known / acceptable species:
SPECIES = [
    'Aerosol-cloud interactions', 'Aerosol-radiation interactions', 'BC',
    'C2F6', 'C3F8', 'C4F10', 'C5F12', 'C6F14', 'C7F16', 'C8F18', 'c-C4F8',
    'CCl4', 'CF4', 'CFC-11', 'CFC-113', 'CFC-114', 'CFC-115', 'CFC-12',
    'CH2Cl2', 'CH3Br', 'CH3CCl3', 'CH3Cl', 'CH4', 'CHCl3', 'CO', 'CO2',
    'CO2 AFOLU', 'CO2 FFI', 'Contrails',
    'Equivalent effective stratospheric chlorine', 'Halon-1202', 'Halon-1211',
    'Halon-1301', 'Halon-2402', 'HCFC-141b', 'HCFC-142b', 'HCFC-22', 'HFC-125',
    'HFC-134a', 'HFC-143a', 'HFC-152a', 'HFC-227ea', 'HFC-23', 'HFC-236fa',
    'HFC-245fa', 'HFC-32', 'HFC-365mfc', 'HFC-4310mee', 'Land use',
    'Light absorbing particles on snow and ice', 'N2O', 'NF3', 'NH3', 'NOx',
    'NOx aviation', 'OC', 'Ozone', 'SF6', 'SO2F2', 'Solar',
    'Stratospheric water vapour', 'Sulfur', 'VOC', 'Volcanic'
]
# default specie:
DEFAULT_SPECIES = ['CO2', 'N2O']
