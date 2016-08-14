'''
Python implementation of Krippendorff's alpha -- inter-rater reliability

(c) 2011 Thomas Grill (http://grrrr.org), 2016 Google Inc.

License: http://creativecommons.org/licenses/by-sa/3.0/

Python 2.7 is required.
'''

try:
    import numpy as np
except ImportError:
    np = None

def nominal_metric(a,b):
    return a != b

def interval_metric(a,b):
    return (a-b)**2

def ratio_metric(a,b):
    return ((a-b)/(a+b))**2

def krippendorff_alpha(data,metric=interval_metric,force_vecmath=False,convert_items=float,missing_items=None,missing_functor=None):
    '''
    Calculate Krippendorff's alpha (inter-rater reliability):

    data is in the format
    [
        {unit1:value, unit2:value, ...},  # worker 1
        {unit1:value, unit3:value, ...},  # worker 2
        ...                               # more workers
    ]
    or
    it is a sequence of (masked) sequences (list, numpy.array, numpy.ma.array, e.g.) with rows corresponding to workers and columns to items

    metric: function calculating the pairwise distance
    force_vecmath: force vector math for custom metrics (numpy required)
    convert_items: function for the type conversion of items (default: float)
    missing_items: indicator for missing items (default: None)
    missing_functor: lambda function that returns true for missing items (default: None)
    '''

    # number of workers
    m = len(data)

    # set of constants identifying missing values
    maskitems = [missing_items]
    if np is not None:
        maskitems.append(np.ma.masked_singleton)

    # convert input data to a dict of items
    units = {}      # unit -> list of values by all workers (the order doesn't matter)
    for worker_d in data:
        try:
            # try if d behaves as a dict
            diter = worker_d.iteritems()
        except AttributeError:
            # sequence assumed for d
            diter = enumerate(worker_d)

        for unit, value in diter:
            if value not in maskitems and (missing_functor is None or not missing_functor(value)):
                units.setdefault(unit, []).append(convert_items(value))

    units = {it: d for it, d in units.iteritems() if len(d) > 1}  # units with pairable values

    n = sum(len(pv) for pv in units.itervalues())  # number of pairable values

    use_numpy = (np is not None) and ((metric in (interval_metric,nominal_metric,ratio_metric)) or force_vecmath)

    Do = 0.
    for grades in units.itervalues():
        if use_numpy:
            gr = np.array(grades)
            Du = sum(np.sum(metric(gr, gri)) for gri in gr)
        else:
            Du = sum(metric(gi, gj) for gi in grades for gj in grades)
        Do += Du / float(len(grades) - 1)
    Do /= float(n)

    De = 0.
    for g1 in units.itervalues():
        if use_numpy:
            d1 = np.array(g1)
            for g2 in units.itervalues():
                De += sum(np.sum(metric(d1, gj)) for gj in g2)
        else:
            for g2 in units.itervalues():
                De += sum(metric(gi, gj) for gi in g1 for gj in g2)
    De /= float(n * (n - 1))

    # print 'n = %d, Do = %f, De = %f' % (n, Do, De)

    return 1 - Do / De

if __name__ == '__main__':
    print "Example from http://en.wikipedia.org/wiki/Krippendorff's_Alpha"

    data = (
        "*    *    *    *    *    3    4    1    2    1    1    3    3    *    3", # worker A
        "1    *    2    1    3    3    4    3    *    *    *    *    *    *    *", # worker B
        "*    *    2    1    3    4    4    *    2    1    1    3    3    *    4", # worker C
    )

    missing = '*' # indicator for missing values
    array = [d.split() for d in data]  # convert to 2D list of string items

    print "nominal metric: %.3f" % krippendorff_alpha(array,nominal_metric,missing_items=missing)
    print "interval metric: %.3f" % krippendorff_alpha(array,interval_metric,missing_items=missing)
