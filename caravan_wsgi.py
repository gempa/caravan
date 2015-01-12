#! /usr/bin/python

"""
Base class implementing a Caravan WSGI application and utilities related to 
server-client requests and responses

(c) 2014, GFZ Potsdam

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 2, or (at your option) any later
version. For more information, see http://www.gnu.org/
"""
from __future__ import print_function

__author__="Riccardo Zaccarelli, PhD <riccardo(at)gfz-potsdam.de, riccardo.zaccarelli(at)gmail.com>"
__date__ ="$Jun 23, 2014 1:15:27 PM$"

import json
import traceback
from cgi import parse_qs, escape #for parsing get method in main page (address bar)

import time
CARAVAN_DEBUG = False; #debug variable, as of Juli 2014 it controls whether exceptions in ResponseHandler should throw the traceback or simply an error message


import os
import miniwsgi
import sys

#todo: check parser dim
#todo: impolement html module to be clear where to write in the html page?
#todo: implement globals.params type for casting?

from caravan.core.core import caravan_run as run
from caravan.core.runutils import RunInfo
import mcerp
import caravan.settings.globalkeys as gk
import caravan.settings.globals as glb
import caravan.fdsnws_events as fe
import json, re
CaravanApp = miniwsgi.App()

#@CaravanApp.route(url='caravan/static/index.html', headers={'Content-Type':'text/html; charset=UTF-8'}) #url='caravan/static/index.html', 
#re.compile(r"\.(?:jpg|jpeg|bmp|gif|png|tif|tiff|js|css|xml)$", re.IGNORECASE)
@CaravanApp.route(url=re.compile(r'(caravan/static/index.html|^$)'), headers={'Content-Type':'text/html; charset=UTF-8'}) #url='caravan/static/index.html', 
def caravan_mainpage(request, response):
    return request.urlbody
    #return open('caravan/static/index.html','rb')

@CaravanApp.route(url='caravan/static/fdsn_query.html', headers={'Content-Type':'text/html; charset=UTF-8'}) #url='caravan/static/index.html', 
def fdsn_query(request, response):
    
    #when this is not a post request, print anyway the table. Therefore:
    try:
        query_url = ""
        try:
            form = request.post
            s = []
            catalog = ''
            for key in form.keys(): 
                l = form.getlist(key)
                if key == 'catalog':
                    catalog=l[0]
                else:
                    par = glb.params[key]
                    fdsn_name = par['fdsn_name']
                    istime = key == gk.TIM
                    
                    if istime:
                        vmin = glb.cast(par,l[0])
                        vmax = glb.cast(par,l[1], round_ceil=True)
                        
                        #fdsn format: 2014-12-07T01:22:03.2Z. Let's conver it
                        vmin = "start{0}={1:04d}-{2:02d}-{3:02d}T{4:02d}:{5:02d}:{6:02d}.{7:d}Z".format(fdsn_name,vmin.year, vmin.month, vmin.day, vmin.hour, vmin.minute, vmin.second,vmin.microsecond)
                        vmax = "end{0}={1:04d}-{2:02d}-{3:02d}T{4:02d}:{5:02d}:{6:02d}.{7:d}Z".format(fdsn_name,vmax.year, vmax.month, vmax.day, vmax.hour, vmax.minute, vmax.second,vmax.microsecond)
                    else:
                        vmin = "min{0}={1}".format(fdsn_name, str(glb.cast(par,l[0],dim=-1))) #-1: needs scalar
                        vmax = "max{0}={1}".format(fdsn_name, glb.cast(par,l[1],dim=-1)) #-1: needs scalar
                    
                    s.append('{0}&{1}'.format(vmin, vmax))
            query_url = fe.FDSN_CATALOG[catalog]+ ('&'.join(s))         
        except:pass   
        
        #define here the ORDER of the columns!
        cols = ("EventLocationName","Time","Latitude","Longitude", "Depth", "Magnitude") #, "EventId")
        submittable_keys = {"Latitude": gk.LAT,"Longitude": gk.LON, "Depth": gk.DEP, "Magnitude": gk.MAG} #numeric are also submittable
    
        value = ""
    
        def esc(s, quote=True): return miniwsgi.escape(s, quote)
        
        def parse_depth(val):
            try:
                if val[0] is not None : val[0] /= 1000
                #if val[1] is not None : val[1] /= 1000 #depth uncertainty SEEMS in km!!!
            except:
                pass
            
        value = [] if not query_url else fe.get_events(query_url, _required_=fe.DEF_NUMERIC_FIELDS, _callback_={fe.F_DEPTH: parse_depth}) #getCaravanEvents(xmlurl)
        
        vals = StringIO()
        vals.write(request.urlbody)        
        vals.write("<table class='fdsn'><thead class='title'><tr>\n")
        vals.write(''.join("<td data-sort='{0}'>{1}</td>".format('num' if v in submittable_keys else 'str', esc(v)) for v in cols))
        vals.write('\n</tr>\n</thead>')
        vals.write("<tbody>")

        for v in value:
            vals.write('<tr>')
            unc = {} if not 'Uncertainty' in v else v['Uncertainty']
            for k in cols:
                tdval = v[k]
                tdstr = str(tdval) if k!="Time" else str(tdval).replace("T"," ").replace("Z","")
                tdsubmit_value = tdstr
                tdsubmit_key = None
                if k in submittable_keys:
                    tdsubmit_key = submittable_keys[k]
                    if k in unc:
                        tdstr+=" &plusmn; " + str(unc[k])
                        pr = glb.params[tdsubmit_key]
                        if 'distrib' in pr:
                            dstr = pr['distrib'].lower()
                            tdsubmit_value = str(tdval) + " " + str(unc[k]/2) if dstr == 'normal' else str(tdval - unc[k]) + " " + str(tdval + unc[k])
                
                vals.write('<td')
                vals.write(' data-value="{}"'.format(esc(tdstr)))
                if tdsubmit_key: vals.write(' data-submit-key="{}" data-submit-value="{}"'.format(esc(tdsubmit_key), esc(tdsubmit_value)))
                vals.write('>{}</td>'.format(tdstr))
            vals.write('</tr>')
        vals.write("</tbody></table>") 
        value = vals.getvalue()
        vals.close()
        
    except Exception as e:
        value = "<span class=error>"+esc(str(e))+"</span>"
        if CARAVAN_DEBUG:
            traceback.print_exc()
    
    s = StringIO()
    s.write(value)
    s.write("\n</body>\n</html>")
    v = s.getvalue()
    s.close()
#         if p == 'catalog':
#             s= cat[p].value + s
#         else
    return v        

#self._default_headers['Content-type']= 'application/json'
#FIXME: CHECK INLINE IMPORT PERFORMANCES!!!

RUNS ={} #stores the runs


@CaravanApp.route(headers={'Content-Type':'application/json'})
def run_simulation(request, response):
    
    jsonData = request.json
    #parse advanced settings:
    
    
    #DO IT HERE, NOW PRIOR TO ANY CALCULATION!!!!
    #FIXME: HANDLE EXCEPTIONS!!!!!
    key_mcerpt_npts = gk.DNP
    mcerp.npts = glb.mcerp_npts if not key_mcerpt_npts in jsonData else glb.cast(key_mcerpt_npts, jsonData[key_mcerpt_npts])
    
    
    runinfo = RunInfo(jsonData)
    
    ret= {}
    if runinfo.status()==1: #running, ok
        runinfo.msg("Process starting at {0} (server time)".format(time.strftime("%c")))
        
        run(runinfo)
        RUNS[runinfo.session_id()] = runinfo #should we add a Lock ? theoretically unnecessary...
        ret = {'session_id':runinfo.session_id(), 'scenario_id':0}
    else:
        ret = {'error': runinfo.errormsg or "Unknown error (please contact the administrator)"}
    
    return response.tojson(ret)

@CaravanApp.route(headers={'Content-Type':'application/json'})
def query_simulation_progress(request, response):
    event = request.json
#     try:
    ret= {}
    if event['session_id'] in RUNS:
        runinfo = RUNS[event['session_id']]

        if event['stop_request']:
            runinfo.stop()

        status = runinfo.status()
        
        done = 100.0 if status > 1 else runinfo.progress()
        ret = {'complete': done}
        msgs = runinfo.msg()
        
        if msgs is not None and len(msgs):
            ret['msg'] = msgs

        #NOTE THAT THE STATUS MIGHT CHANGE IN PROGRESS< AS IT MIGHT SET AN ERROR MSG
        #INSTEAD OF RE_QUERYING THE STATUS, WE QUERY THE ERROR
        if runinfo.errormsg: #status == 3:
            ret['error'] = runinfo.errormsg

    else:
        ret = {"error":"query progress error: session id {0} not found".format(str(event['session_id']))}
#     except:
#         import traceback
#         from StringIO import StringIO
#         s = StringIO()
#         traceback.print_exc(s)
#         s.close()
#         ret = {"error":s.getvalue()}
        
    return response.tojson(ret)


@CaravanApp.route(headers={'Content-Type':'application/json'})
def query_simulation_data(request, response):
    event = request.json
    session_id = event['session_id']
    print("session id"+str(session_id))
    conn = glb.connection(async=True)
    #query:
    #note: ::json casts as json, not as jason-formatted string
    #::double precision is NECESSARY as it returns a json convertible value, otherwise array alone returns python decimals
    #which need to be converted to double prior to json dumps

    data = conn.fetchall("""SELECT 
ST_AsGeoJSON(ST_Transform(G.the_geom,4326))::json AS geometry, GM.geocell_id, GM.ground_motion, risk.social_conseq.fatalities_prob_dist
FROM 
processing.ground_motion as GM
LEFT JOIN 
risk.social_conseq ON (risk.social_conseq.geocell_id = GM.geocell_id and risk.social_conseq.session_id = GM.session_id)
LEFT JOIN 
exposure.geocells as G ON (G.gid = GM.geocell_id)
WHERE 
GM.session_id=%s""",(session_id,)) #(session_id,))

    #conn.conn.commit()
    conn.close()
    
    #HYPOTHESES:
    #1) The query above returns a table T.
    #2) a single T row (R) corresponds to a geojson feature F
    #3) A geojson feature F has the fields
    #{
    #    type: 'Feture', 
    #    gemoetry : dict, 
    #    id: number_or_string, 
    #    properties:{
    #       key1: {data: usually_array, value:numeric_scalar},
    #       ...
    #       keyN: {data: usually_array, value:numeric_scalar},
    #    }
    #}   
    #4) each R contains AT LEAST the field 'geometry' AT INDEX 0 (see query above)
    #and the id field at index 1
    #5) Any other column of R will be set as key of field 'properties' of F, the table value
    # will be associated to the data property key, and value is user-defined (see below)
    # 
    #6) captions are attached to the parent object wrapping eeach feature and 
    #will be used to check whether the data for a oparticular layergroup
    #is present
    
    #Defined the columns to be set as properties (excluding geometry):
    captions = {gk.MSI:2, gk.FAT:3, gk.ECL: 4} 
    
    def process(name, row, row_index):
        try:
            data = row[row_index]
            if name == gk.MSI: #return the median
                #pop last element, which is the median according to core.py
                m = data.pop() #removes and returns the last index
                return data, m
            elif name == gk.FAT: #return INDEX OF max value
                remVal = 1
                max = 0
                ind_of_max = 0
                i = 0
                for n in data:
                    if n > max: 
                        max = n
                        ind_of_max = i
                    remVal -= n
                    if remVal < max: break #< not <=: priority to higher value, if two or more are equal
                    i += 1

                return data, ind_of_max
            elif name == gk.ECL: #economic losses, to be implemented
                pass
        except: pass #exception: return None, None below
        #elif ... here implement new values for newly added names
        return None, None
    
    dataret = {"type": "FeatureCollection", "features": None, "captions": {k:"" for k in captions}}
    features = [] #pre-allocation doesn't seem to matter. See e.g. http://stackoverflow.com/questions/311775/python-create-a-list-with-initial-capacity
    
    for row in data:
        cell = {'geometry': row[0], 'id':row[1], 'type':'Feature', 'properties':{}}
        for name in captions:
            index = captions[name]
            data, value = process(name, row, index)
            property = {'data': data, 'value': value}
            cell['properties'][name] = property

        features.append(cell)
    dataret['features'] = features
#     dataret['percentiles_caption'] = glb.percentiles

    return response.tojson(dataret)


def _mtime(file, files):
    r = 3;
    t = (round(os.path.getmtime(filename),r) if os.path.exists(filename) else None for filename in files)
    tmax = None
    for tt in t:
        if tt is None: continue
        if tmax is None or tt>tmax: tmax = tt 
        #we need to round mtimes cause apparently thy are difference even if they "aren't"
    if tmax is None: #equal to tmax so that if we modified fileout itself, it rebuilds it
        return None
    
    if not os.path.exists(file): return tmax
    
    t0 = round(os.path.getmtime(file),r)
    return None if t0==tmax else tmax


"returns the modification time of file according to files. "
def needs_update(file, files):
    return _mtime(file, files) is not None

def set_mtime(file, files):
    mt = _mtime(file, files);
    if mt is None: return
    os.utime(file, (os.path.getatime(file), mt))
    
from StringIO import StringIO #needs update to Python3!!!!
def create_main_page(): #FIXME: check compatibility with io in python3
    
    source = "caravan/static/index_template.html"
    dest = "caravan/static/index.html"
    
    check_sources = [source, "caravan/settings/globals.py", "caravan/settings/user_options.py"]
    if not needs_update(dest, check_sources): return
    
    if CARAVAN_DEBUG: print("Updating {}".format(dest))
    f = open(source,'r')
    k = f.read()
    s = StringIO()
    f.close()
    import re
    
    r = re.compile("\{\%\\s*(.*?)\\s*\%\}",re.DOTALL)
    
    lastidx = 0
    for m in r.finditer(k,lastidx):
        if m.start() > lastidx:
            s.write(k[lastidx: m.start()])
        
        ztr = m.group()
        if m is not None and len(m.groups())==1:
            val = glb.get(m.group(1))
            ztr = "" if val is None else str(val)
        
        s.write(ztr)
        lastidx = m.end()
    
    l = len(k)
    if lastidx < l:
        s.write(k[lastidx: l])
        
    f = open(dest,'w')
    k = f.write(s.getvalue())
    s.close()
    f.close()
    
    set_mtime(dest, check_sources)

import imp
from importlib import import_module
from types import ModuleType
# import lang.default as lang_default
def create_dict_js(): #FIXME: check compatibility with io in python3
    DEFAULT_LANG = "en" #move from here?
    dict_dir = "caravan/settings/lang"
    files = [ os.path.join(dict_dir,f) for f in os.listdir(dict_dir) if os.path.splitext(f)[1].lower() == '.py' ] #os.path.isfile(os.path.join(dict_dir,f)) ]
    
    dest = "caravan/static/libs/js/lang_dict.js"
    
    #print(str(files)+ " "+str(needs_update(dest, files)))
    source = "caravan/static/libs/js/lang_dict_template.js"
    
    check_sources = list(files)
    check_sources.append(source)
    if not needs_update(dest, check_sources): return
    
    if CARAVAN_DEBUG: print("Updating {}".format(dest))
    
    fout = StringIO()
    fout.write('{\n');
    first = True
    
#     gks = set()
#     for d in dir(gk):
#         if len(d)>1 and d[:1] == "_": continue #len(d)<4 or not (d[:2] == "__" and d[-2:] == "__"):
#         gks.add(gk.__dict__[d])
    
#     print(str(gks))

    _quote_ = glb.dumps
    
    gmpez = {g.__name__ : g for g in glb.def_gmpes.values()}
    
    for f in files:
        mod_name,file_ext = os.path.splitext(os.path.split(f)[-1])

        if mod_name.lower() == "__init__" or file_ext.lower() != '.py' or not os.path.isfile(f): continue #for safety (should not be the case
        
        
        full_name = os.path.splitext(f)[0].replace(os.path.sep, '.')
#         print("{0} full path: {1}".format(mod_name, full_name))
        
        py_mod = import_module(full_name)
        
#         print("modname: "+py_mod.__name__)
        
        py_mod_dir = dir(py_mod)
#         print("dir: "+str(py_mod_dir))

        if first: first=False
        else: fout.write(",\n")
        
        fout.write(mod_name)
        fout.write(" : {")
        
        ffirst = True
        
        for k in py_mod_dir: # gks:
            if len(k)>1 and k[:1] == "_": continue
            
            val = py_mod.__dict__[k]
            if isinstance(val, ModuleType): continue
            
            if ffirst: ffirst = False
            else: fout.write(",\n")
            
            
            #handle gmpes (ipes):
            if k in gmpez and "_ipe_dist_bounds_text" in py_mod.__dict__ and "_ipe_mag_bounds_text" in py_mod.__dict__:
                ge = gmpez[k]
                val = val+"<br>"+py_mod.__dict__["_ipe_mag_bounds_text"] + str(list(ge.m_bounds))+"<br>"+py_mod.__dict__["_ipe_dist_bounds_text"] + str(list(ge.d_bounds))+("<br><i>"+ge.ref+"</i>" if ge.ref else "")
            
            var  = _quote_(val)
            
            #"[{}]".format(','.join(_quote_(str(v)) for v in val)) if hasattr(val, "__iter__") else '""' if val is None else _quote_(str(val))

            
            fout.write(k)
            fout.write(" : ")
            fout.write(var)
        
        fout.write("}\n")
        
    fout.write("};")
    
    sourcen = open(source, 'r')
    sn = sourcen.read()
    sourcen.close()
    sn = sn.replace("{% DICT %}",fout.getvalue())
    sn = sn.replace("{% DEFAULT_LANG %}", DEFAULT_LANG)
    fout.close()
    
    fout = open(dest,'w')
    fout.write(sn)
    fout.close()
    set_mtime(dest, check_sources)


 
# 
# def create_dyn_file(filein, fileout, other_files, func):
#     fileout="caravan.html"
#     filein = "index.html"
#     r = 3;
#     if os.path.exists(fileout):
#         t0 = round(os.path.getmtime(fileout),r)
#         files = [filein, "globals.py", "settings.py", "static/libs/js/lang_dict.js"]
#         #we need to round mtimes cause apparently thy are difference even if they "aren't"
#         t = [round(os.path.getmtime(filename),r) if os.path.exists(filename) else t0-1 for filename in files]
#         tmax = max(t)
#         if t0 == tmax: #equal to tmax so that if we modified fileout itself, it rebuilds it
#             return
#         
#     if CARAVAN_DEBUG: print("CREATING DYNAMIC FILE!!! t0="+str(t0)+" != tmax= "+str(tmax))
#     func(filein, fileout)
#     os.utime(fileout, (os.path.getatime(fileout), tmax)) #set ACCESS AND modification time
#     if CARAVAN_DEBUG: print("t0= " + str(os.path.getmtime(fileout)))


#execute files:
create_main_page()
create_dict_js()

if(CARAVAN_DEBUG):
    print(str(CaravanApp))  
