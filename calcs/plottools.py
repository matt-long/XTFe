from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from matplotlib import colors

import numpy as np

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def plot_grid_dims(n):
    ncol = int(np.sqrt(n))
    nrow = int(((n/ncol)+n%ncol))
    return nrow,ncol

#---------------------------------------------------------
#--- function
#---------------------------------------------------------

def adjust_pop_grid(tlon,tlat,field):
    nj = tlon.shape[0]
    ni = tlon.shape[1]
    xL = int(ni/2 - 1)
    xR = int(xL + ni)

    tlon = np.where(np.greater_equal(tlon,min(tlon[:,0])),tlon-360.,tlon)
    lon  = np.concatenate((tlon,tlon+360.),1)
    lon = lon[:,xL:xR]

    if ni == 320:
        lon[367:-3,0] = lon[367:-3,0]+360.
    lon = lon - 360.
    lon = np.hstack((lon,lon[:,0:1]+360.))
    if ni == 320:
        lon[367:,-1] = lon[367:,-1] - 360.

    #-- trick cartopy into doing the right thing:
    #   it gets confused when the cyclic coords are identical
    lon[:,0] = lon[:,0]-1e-8

    #-- periodicity
    lat  = np.concatenate((tlat,tlat),1)
    lat = lat[:,xL:xR]
    lat = np.hstack((lat,lat[:,0:1]))

    field = np.ma.concatenate((field,field),1)
    field = field[:,xL:xR]
    field = np.ma.hstack((field,field[:,0:1]))
    field = np.ma.masked_where(np.isnan(field),field)
    
    return lon,lat,field

#-------------------------------------------------------------------------------
#-- class
#-------------------------------------------------------------------------------

class MidPointNorm(colors.Normalize):

    def __init__(self, midpoint=0, vmin=None, vmax=None, clip=False):
        colors.Normalize.__init__(self,vmin, vmax, clip)
        self.midpoint = midpoint

    def __call__(self, value, clip=None):
        if clip is None:
            clip = self.clip

        result, is_scalar = self.process_value(value)

        self.autoscale_None(result)
        vmin, vmax, midpoint = self.vmin, self.vmax, self.midpoint

        if not (vmin < midpoint < vmax):
            raise ValueError("midpoint must be between maxvalue and minvalue.")
        elif vmin == vmax:
            result.fill(0) # Or should it be all masked? Or 0.5?
        elif vmin > vmax:
            raise ValueError("maxvalue must be bigger than minvalue")
        else:
            vmin = float(vmin)
            vmax = float(vmax)
            if clip:
                mask = np.ma.getmask(result)
                result = np.ma.array(np.clip(result.filled(vmax), vmin, vmax),
                                  mask=mask)

            # ma division is very slow; we can take a shortcut
            resdat = result.data

            #First scale to -1 to 1 range, than to from 0 to 1.
            resdat -= midpoint
            resdat[resdat>0] /= abs(vmax - midpoint)
            resdat[resdat<0] /= abs(vmin - midpoint)

            resdat /= 2.
            resdat += 0.5
            result = np.ma.array(resdat, mask=result.mask, copy=False)

        if is_scalar:
            result = result[0]
        return result


    def inverse(self, value):
        if not self.scaled():
            raise ValueError("Not invertible until scaled")
        vmin, vmax, midpoint = self.vmin, self.vmax, self.midpoint

        if cbook.iterable(value):
            val = np.ma.asarray(value)
            val = 2 * (val-0.5)
            val[val>0]  *= abs(vmax - midpoint)
            val[val<0] *= abs(vmin - midpoint)
            val += midpoint
            return val
        else:
            val = 2 * (val - 0.5)
            if val < 0:
                return  val*abs(vmin-midpoint) + midpoint
            else:
                return  val*abs(vmax-midpoint) + midpoint

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def nice_levels(cmin,cmax,max_steps,outside=False):
    '''
    Return nice contour levels
    outside indicates whether the contour should be inside or outside the bounds
    '''
    import sys

    table = [ 1.0,2.0,2.5,4.0,5.0,
              10.0,20.0,25.0,40.0,50.0,
              100.0,200.0,250.0,400.0,500.0]

    am2 = 0.
    ax2 = 0.
    npts = 15

    d = 10.**(np.floor(np.log10(cmax-cmin))-2.)

    u = sys.float_info.max
    step_size = sys.float_info.max

    if outside:
        for i in range(npts):
            t = table[i] * d
            am1 = np.floor(cmin/t) * t
            ax1 = np.ceil(cmax/t) * t

            if (i == npts-1 and step_size == u) or ( (t <= step_size) and ((ax1-am1)/t <= (max_steps-1)) ):
                step_size = t
                ax2 = ax1
                am2 = am1
    else:
        for i in range(npts):
            t = table[i] * d
            am1 = np.ceil(cmin/t) * t
            ax1 = np.floor(cmax/t) * t

            if (i == npts-1 and step_size == u) or ( (t <= step_size) and ((ax1-am1)/t <= (max_steps-1)) ):
                step_size = t
                ax2 = ax1
                am2 = am1

    min_out = am2
    max_out = ax2

    return np.arange(min_out,max_out+step_size,step_size)

#-------------------------------------------------------------------------------
#-- class
#-------------------------------------------------------------------------------

class contour_label_format(float):
    def __repr__(self):
        str = '%.1f' % (self.__float__(),)
        if str[-1] == '0':
            return '%.0f' % self.__float__()
        else:
            return '%.1f' % self.__float__()


#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def canvas_map_contour_overlay(lon,lat,z,
                               contour_specs,
                               units,
                               fig,
                               ax,
                               row,col):


    #-- make canvas
    ax = fig.add_subplot(gridspec[row,col],projection=ccrs.Robinson(central_longitude=305.0))
    ax.set_global()

    #-- make masked
    z = np.ma.masked_invalid(z)

    #-- make filled contours
    cf = ax.contourf(lon,lat,z,
                     transform=ccrs.PlateCarree(),
                     **contour_specs)
    #-- rasterize
    zorder = 0
    for contour_level in cf.collections:
        contour_level.set_zorder(zorder)
        contour_level.set_rasterized(True)

    #-- add contour lines
    cs = ax.contour(lon,lat,z,
                    colors='k',
                    levels = contour_specs['levels'],
                    linewidths = 0.5,
                    transform=ccrs.PlateCarree(),
                    zorder=len(cf.collections)+10)

    #-- add contour labels
    cs.levels = [contour_label_format(val) for val in cs.levels]
    fmt = '%r'
    lb = plt.clabel(cs, fontsize=6,
                   inline = True,
                   fmt=fmt)

    #-- add land mask
    land = ax.add_feature(
        cartopy.feature.NaturalEarthFeature('physical','land','110m',
                                            edgecolor='face',
                                            facecolor='black'))
    #land = ax.add_feature(cartopy.feature.LAND, zorder=100,
    #                       edgecolor='black', facecolor='black')

    #-- add colorbar
    i = 0
    while True:
        i += 1
        try:
            gridspec[i]
        except:
            break
    len_gs = i
    if len_gs == 1:
        shrink_factor = 0.35
    else:
        shrink_factor = 0.75

    cb = fig.colorbar(cf,ax = ax,
                      ticks = contour_specs['levels'],
                      orientation = 'vertical',
                      shrink = shrink_factor)
    cb.ax.set_title(units)

    return {'ax':ax,'cf':cf,'cs':cs,'lb':lb,'cb':cb}

contour_specs = {'O2' : {'levels' : np.concatenate((np.arange(0,5,1),np.arange(5,10,2),np.arange(10,30,5),np.arange(30,70,10),np.arange(80,150,20),np.arange(150,325,25))),
                         'norm' : MidPointNorm(midpoint=50.),
                         'extend' : 'max','cmap':'PuOr'},
                 'NO3' : {'levels' : [0,0.1,0.2,0.3,0.4,0.6,0.8,1.,1.5,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,34,38,42],
                          'norm' : MidPointNorm(midpoint=2.),
                          'extend' : 'max','cmap':'PRGn'},
                 'PO4' : {'levels' : [0,0.01,0.02,0.04,0.06,0.08,0.1,0.14,0.18,0.22,0.26,0.3,0.34,0.38,0.42,0.46,0.5,0.6,0.7,0.8,0.9,1,1.2,1.4,1.6,1.8,2,2.4,2.8,3.2],
                          'norm' : MidPointNorm(midpoint=0.8),
                          'extend' : 'max','cmap':'PRGn'},
                 'SiO3' : {'levels' : np.concatenate((np.arange(0,10,1),np.arange(10,50,5),np.arange(50,100,10),np.arange(100,200,20))),
                           'norm' : MidPointNorm(midpoint=5.),
                           'extend' : 'max','cmap':'PRGn'}
                 }
