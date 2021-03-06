# -*- encoding: utf-8 -*-

import urllib
from lxml import etree
import json
from datetime import datetime
import time
import sys
sys.path.append('../..')
from models import *
import pandas as pd
import numpy as np


class EfetchError(Exception):
    pass

class EutilitiesConnectionError(Exception):
    pass

class MultipleBiosampleError(Exception):
    pass

#fn to try to get request from eutilities (as part e.g. get_links fn); if connection error for some reason raise efetch error
def geturl_with_retry(MaxRetry,url):
        while(MaxRetry >= 0):
            try:
                base = urllib.urlopen(url)
                base_tree = etree.parse(base)
                base.close()
                base_xml = base_tree.getroot()
                return base_xml
            except Exception:
                print "Internet connectivity Error Retrying in 5 seconds"
                time.sleep(5)
                MaxRetry=MaxRetry - 1

        errorToWrite = ScrapeError(uid="url",error_msg="eutilities connection error",function="geturl_with_retry",date_scraped=datetime.now())
        db.session.add(errorToWrite)
        db.session.commit()
        raise EutilitiesConnectionError("eutilities connection error")

def get_retstart_list(url):
    #define retstarts need for get_uid_list eutilities requests - since can only get 100,000 at a time, need to make multiple queries to get total list
    #find out count of UIDs going to pull from SRA
    g = urllib.urlopen(url)
    count_tree = etree.parse(g)
    g.close()
    count_xml = count_tree.getroot()
    num_uids = count_xml.findtext("Count")
    print 'number of publicly available UIDs in SRA: %s' % num_uids
    num_queries = 1+int(num_uids)//100000  #number of queries to do, with shifting retstart
    retstart_list = [i*100000 for i in range(num_queries)]
    print 'retstarts to use: %s' % retstart_list
    return retstart_list

def get_uid_list(ret_list):
    #scrape UIDs into list
    uid_list = []
    for retstart in ret_list:
        uid_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=sra&term=public&field=ACS&tool=metaseq&email=metaseekcloud%40gmail.com&retmax=100000&retstart='+str(retstart)
        uid_xml = geturl_with_retry(MaxRetry=5,url=uid_url)
        try:
            print "appending %s accessions with retstart %s" % (len(uid_xml.find("IdList").findall("Id")), retstart)
            #add uids to list of accessions
            for id in uid_xml.find("IdList").iterchildren():
                value = id.text
                uid_list.append(value)
        except Exception: #this will fail if there is no IdList (404 response)
            errorToWrite = ScrapeError(uid="url",error_msg="eutilities connection error",function="get_uid_list",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            print "eutilities connection error getting batch with retstart %s; skipping to next retstart" % (retstart)
            pass

    return uid_list

def get_batches(uid_list, batch_size=200):
    starts = range(0,len(uid_list),batch_size)
    ends = range(batch_size,len(uid_list),batch_size)
    ends.append(len(uid_list))
    batches = [list(a) for a in zip(starts, ends)]
    return batches


def get_srx_metadata(batch_uid_list):
    print "...Querying API and parsing SRX XML..."
    s_parse_time = datetime.now()
    srx_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&tool=metaseq&email=metaseekcloud%40gmail.com'
    for key in batch_uid_list:
        #this makes url with end &id=###&id=###&id=### - returns a set of links in order of sra uids
        srx_url = srx_url+'&id='+str(key)
    #srx_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&tool=metaseq&email=metaseekcloud%40gmail.com&id='+str(batch_uid_list)[1:-1]
    sra_xml = geturl_with_retry(MaxRetry=5,url=srx_url)

    try: #sometimes the url is parsed with lxml but is an error xml output from eutilities; this step fails in that case
        sra_samples = sra_xml.findall("EXPERIMENT_PACKAGE")
    except Exception:
        errorToWrite = ScrapeError(uid="url",error_msg="eutilities connection error",function="get_srx_metadata",date_scraped=datetime.now())
        db.session.add(errorToWrite)
        db.session.commit()
        raise EutilitiesConnectionError('eutilities connection error')

    print "......parsing done for %s srxs in %s" % (len(batch_uid_list),(datetime.now()-s_parse_time))
    print "...scraping srx metadata..."
    s_scrape_time = datetime.now()
    sdict = {}
    rdict = {}

    #if the length of sra_samples != length of batch_uid_list, then one or more of the uids did not return an efetch (maybe it's not public even though it shows up in esearch);
    #if this is the case, raise EfetchError which will skip this batch of 500
    if len(sra_samples)!=len(batch_uid_list):
        raise EfetchError('length srx batch does not equal length returned efetches! skipping this batch')

    for which,sra_sample in enumerate(sra_samples): #the order of experiment_packages ARE in order of sra ids given - that's good
        srx_dict = {}
        srx_uid = str(batch_uid_list[which])
        #print "--scraping srx metadata for sample uid %s, %s out of %s" % (srx_uid, which+1,len(sra_samples))

        srx_dict['db_source_uid'] = srx_uid
        srx_dict['db_source'] = 'SRA'
        srx_dict['expt_link'] = "https://www.ncbi.nlm.nih.gov/sra/"+str(srx_uid)

        #There are 7 top tag groups. Have to scrape data a little different for each: ['EXPERIMENT','SUBMISSION','Organization','STUDY','SAMPLE','Pool','RUN_SET']

        ###EXPERIMENT -
        try:
            srx_dict['expt_id'] = sra_sample.find("EXPERIMENT").find("IDENTIFIERS").findtext("PRIMARY_ID")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError expt_id",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['expt_title'] = sra_sample.find("EXPERIMENT").findtext("TITLE")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError expt_title",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict["study_id"] = sra_sample.find("EXPERIMENT").find("STUDY_REF").find("IDENTIFIERS").findtext("PRIMARY_ID")
        except AttributeError:
            #don't log error because can get it from the study identifiers anyway
            pass
        try:
            srx_dict['expt_design_description'] = sra_sample.find("EXPERIMENT").find("DESIGN").findtext("DESIGN_DESCRIPTION")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError expt_design_description",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['sample_id'] = sra_sample.find("EXPERIMENT").find("DESIGN").find("SAMPLE_DESCRIPTOR").get("accession")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError sample_id",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['library_name'] = sra_sample.find("EXPERIMENT").find("DESIGN").find("LIBRARY_DESCRIPTOR").findtext("LIBRARY_NAME")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError library_name",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['library_strategy'] = sra_sample.find("EXPERIMENT").find("DESIGN").find("LIBRARY_DESCRIPTOR").findtext("LIBRARY_STRATEGY")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError library_strategy",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['library_source'] = sra_sample.find("EXPERIMENT").find("DESIGN").find("LIBRARY_DESCRIPTOR").findtext("LIBRARY_SOURCE").lower()
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError library_source",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            ###change library_selection to MIxS field library_screening_strategy (cv for SRA, not for MIxS)
            srx_dict['library_screening_strategy'] = sra_sample.find("EXPERIMENT").find("DESIGN").find("LIBRARY_DESCRIPTOR").findtext("LIBRARY_SELECTION")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError library_screening_strategy",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            ###change library_layout to MIxS field library_construction_method - cv single | paired
            layout = sra_sample.find("EXPERIMENT").find("DESIGN").find("LIBRARY_DESCRIPTOR").find("LIBRARY_LAYOUT").getchildren()[0].tag.lower()
            srx_dict['library_construction_method'] = layout
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError library_construction_method",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['library_construction_protocol'] = sra_sample.find("EXPERIMENT").find("DESIGN").find("LIBRARY_DESCRIPTOR").findtext("LIBRARY_CONSTRUCTION_PROTOCOL")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError library_construction_protocol",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            ###change platform to MIxS field sequencing_method - cv in SRA (not in MIxS)
            if len(sra_sample.find("EXPERIMENT").find("PLATFORM").getchildren())>1:
                #find the one that's actually a tag
                for platform in sra_sample.find("EXPERIMENT").find("PLATFORM").getchildren():
                    if type(platform.tag) is str:
                        srx_dict['sequencing_method'] = platform.tag.lower()
                        srx_dict['instrument_model'] = platform.findtext("INSTRUMENT_MODEL")
            else:
                srx_dict['sequencing_method'] = sra_sample.find("EXPERIMENT").find("PLATFORM").getchildren()[0].tag.lower()
                srx_dict['instrument_model'] = sra_sample.find("EXPERIMENT").find("PLATFORM").getchildren()[0].findtext("INSTRUMENT_MODEL")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError sequencing_method or instrument_model",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        ###SUBMISSION - just need the submission id
        try:
            srx_dict['submission_id'] = sra_sample.find("SUBMISSION").find("IDENTIFIERS").findtext("PRIMARY_ID")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError submission_id",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        ###Organization - name, address, and contact;
        if sra_sample.find("Organization") is not None: #this is missing fairly often so don't try unless it's there
            try:
                srx_dict['organization_name'] = sra_sample.find("Organization").findtext("Name")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError organization_name",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                address = ''
                if sra_sample.find("Organization").find("Address") is not None: #really common not to have this
                    for line in sra_sample.find("Organization").find("Address").iterchildren():
                        address = address+line.text+', '
                    address = address[:-2]
                srx_dict['organization_address'] = address
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError organization_address",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                if len(sra_sample.find("Organization").findall("Contact"))>0:
                    contacts = ''
                    for contact in sra_sample.find("Organization").findall("Contact"):
                        try:
                            name = contact.find("Name").find("First").text+' '+contact.find("Name").find("Last").text
                        except AttributeError:
                            name=''
                        email = contact.get('email')
                        contacts = contacts + name + ', ' + email + ', '
                    srx_dict['organization_contacts'] = contacts[:-2] # remove trailing comma and space
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError organization_contacts",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass

        ###STUDY -
        try:
            srx_dict['study_id'] = sra_sample.find("STUDY").find("IDENTIFIERS").findtext("PRIMARY_ID")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError study_id",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            for external in sra_sample.find("STUDY").find("IDENTIFIERS").iterchildren("EXTERNAL_ID"):
                if external.get("namespace")=='BioProject':
                    srx_dict['bioproject_id'] = external.text
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError bioproject_id",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['study_title'] = sra_sample.find("STUDY").find("DESCRIPTOR").findtext("STUDY_TITLE")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError study_title",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
        ###rename existing_study_type to study_type
            if sra_sample.find("STUDY").find("DESCRIPTOR").find("STUDY_TYPE").get("existing_study_type")=="Other":
                srx_dict['study_type'] = 'Other'
                if sra_sample.find("STUDY").find("DESCRIPTOR").find("STUDY_TYPE").get("add_study_type") is not None:
                    srx_dict['study_type_other'] = sra_sample.find("STUDY").find("DESCRIPTOR").find("STUDY_TYPE").get("add_study_type")
            else:
                srx_dict['study_type'] = sra_sample.find("STUDY").find("DESCRIPTOR").find("STUDY_TYPE").get("existing_study_type")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError study_type or study_type_other",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            srx_dict['study_abstract'] = sra_sample.find("STUDY").find("DESCRIPTOR").findtext("STUDY_ABSTRACT")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError study_abstract",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            study_links = {}
            if sra_sample.find("STUDY").find("STUDY_LINKS") is not None: #really common to not have this, so keep so don't get a million error logs
                for study_link in sra_sample.find("STUDY").find("STUDY_LINKS").iterchildren():
                    if study_link.find("XREF_LINK") is not None:
                        study_links[study_link.find("XREF_LINK").findtext("DB")] = study_link.find("XREF_LINK").findtext("ID")
                    if study_link.find("URL_LINK") is not None:
                        study_links[study_link.find("URL_LINK").findtext("LABEL")] = study_link.find("URL_LINK").findtext("URL")
            srx_dict['study_links'] = json.dumps(study_links) #replaced str() coercion with JSON str for db
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError study_links",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            study_attributes = {}
            if sra_sample.find("STUDY").find("STUDY_ATTRIBUTES") is not None: #really common not to have this
                for attr in sra_sample.find("STUDY").find("STUDY_ATTRIBUTES").iterchildren():
                    study_attributes[attr.findtext("TAG")] = attr.findtext("VALUE")
            srx_dict['study_attributes'] = json.dumps(study_attributes)  #replaced str() coercion with JSON str for db
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError study_attributes",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        ###SAMPLE - get some BioSample stuff that's in easier format here: sample id, biosample id (if exists; it should but sometimes doesn't); also title, sample name stuff, and description; rest get from biosample scraping
        #it's common to not have a Sample tag (Biosample not imported or something, but elink usually exists); just ignore in this case
        if sra_sample.find("SAMPLE") is not None:
            try:
                srx_dict['sample_id'] = sra_sample.find("SAMPLE").find("IDENTIFIERS").findtext("PRIMARY_ID")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError sample_id",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                for external in sra_sample.find("SAMPLE").find("IDENTIFIERS").iterchildren("EXTERNAL_ID"):
                    if external.get("namespace")=='BioSample':
                        srx_dict['biosample_id'] = external.text
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError biosample_id",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                srx_dict['sample_title'] = sra_sample.find("SAMPLE").findtext("TITLE")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError sample_title",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                srx_dict['ncbi_taxon_id'] = sra_sample.find("SAMPLE").find("SAMPLE_NAME").findtext("TAXON_ID")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError ncbi_taxon_id",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                srx_dict['taxon_scientific_name'] = sra_sample.find("SAMPLE").find("SAMPLE_NAME").findtext("SCIENTIFIC_NAME")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError taxon_scientific_name",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                srx_dict['taxon_common_name'] = sra_sample.find("SAMPLE").find("SAMPLE_NAME").findtext("COMMON_NAME")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError taxon_common_name",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                srx_dict['sample_description'] = sra_sample.find("SAMPLE").findtext("DESCRIPTION")
            except AttributeError:
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError sample_description",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass

        ###Pool - skip, redundant

        ###RUN_SET - record stats for each run as list, for best run (maxrun, run for which total_num_reads is largest) as single value
        run_ids = []
        total_num_reads = []
        total_num_bases = []
        download_size = []
        avg_read_length = []
        baseA_count = []
        baseC_count = []
        baseG_count = []
        baseT_count = []
        baseN_count = []
        gc_percent = []
        read_quality_counts = []
        try:
            srx_dict['num_runs_in_accession'] = len(sra_sample.find("RUN_SET").findall("RUN"))
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError num_runs_in_accession",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        try:
            run_list = sra_sample.find("RUN_SET").findall("RUN")
        except AttributeError:
            run_list = []
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError prob missing run_set",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        for run in run_list:
            try:
                run_id = run.get("accession")
                run_ids.append(run_id)
            except AttributeError:
                run_id = None
                run_ids.append(run_id)
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="AttributeError run missing accession",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                if run.get("total_spots") is not None: #really common to be missing this, don't log error
                    total_num_reads.append(int(run.get("total_spots")))
                else:
                    total_num_reads.append(None)
            except (TypeError, ValueError) as e: #will be typeerror if int(None); valueerror if can't make int (is string or weird characters)
                total_num_reads.append(None)
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" library_reads_sequenced",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                if run.get("total_bases") is not None:
                    total_num_bases.append(int(run.get("total_bases")))
                else:
                    total_num_bases.append(None)
            except (TypeError, ValueError) as e:
                total_num_bases.append(None)
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" total_num_bases",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                if run.get("size") is not None:
                    download_size.append(int(run.get("size")))
                else:
                    download_size.append(None)
            except (TypeError, ValueError) as e:
                download_size.append(None)
                errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" download_size",function="get_srx_metadata",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                pass
            try:
                base_list = run.find("Bases").findall("Base")
            except AttributeError:
                base_list = []
                pass
            if len(base_list)!=5: #if doesn't have all five bases counted, ignore
                baseA_count.append(None)
                baseC_count.append(None)
                baseG_count.append(None)
                baseT_count.append(None)
                baseN_count.append(None)
                gc_percent.append(None)
                countA=None
                countC=None
                countG=None
                countT=None
            else:
                #if base_list is length 5, but has weird values like 0,1,2,3,. (see srx uid 4172335), only use if has the values it should
                should_be = ['A', 'C', 'G', 'T', 'N']
                nucleotides = []
                for base in base_list:
                    nucleotides.append(base.get("value"))
                if set(nucleotides)!=set(should_be): #only try to get base counts and gc percent if tags are right
                    baseA_count.append(None)
                    baseC_count.append(None)
                    baseG_count.append(None)
                    baseT_count.append(None)
                    baseN_count.append(None)
                    gc_percent.append(None)
                    countA=None
                    countC=None
                    countG=None
                    countT=None
                elif set(nucleotides)==set(should_be):
                    for base in base_list:
                        try:
                            if base.get("value")=="A":
                                baseA_count.append(int(base.get("count")))
                                countA = int(base.get("count"))
                        except (TypeError, ValueError) as e:
                            baseA_count.append(None)
                            countA=None
                            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" baseA_count",function="get_srx_metadata",date_scraped=datetime.now())
                            db.session.add(errorToWrite)
                            db.session.commit()
                            pass
                        try:
                            if base.get("value")=="C":
                                baseC_count.append(int(base.get("count")))
                                countC = int(base.get("count"))
                        except (TypeError, ValueError) as e:
                            baseC_count.append(None)
                            countC=None
                            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" baseC_count",function="get_srx_metadata",date_scraped=datetime.now())
                            db.session.add(errorToWrite)
                            db.session.commit()
                            pass
                        try:
                            if base.get("value")=="G":
                                baseG_count.append(int(base.get("count")))
                                countG = int(base.get("count"))
                        except (TypeError, ValueError) as e:
                            baseG_count.append(None)
                            countG=None
                            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" baseG_count",function="get_srx_metadata",date_scraped=datetime.now())
                            db.session.add(errorToWrite)
                            db.session.commit()
                            pass
                        try:
                            if base.get("value")=="T":
                                baseT_count.append(int(base.get("count")))
                                countT = int(base.get("count"))
                        except (TypeError, ValueError) as e:
                            baseT_count.append(None)
                            countT=None
                            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" baseT_count",function="get_srx_metadata",date_scraped=datetime.now())
                            db.session.add(errorToWrite)
                            db.session.commit()
                            pass
                        try:
                            if base.get("value")=="N":
                                baseN_count.append(int(base.get("count")))
                                countN = int(base.get("count"))
                        except (TypeError, ValueError) as e:
                            baseN_count.append(None)
                            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" baseN_count",function="get_srx_metadata",date_scraped=datetime.now())
                            db.session.add(errorToWrite)
                            db.session.commit()
                            pass
                    try:
                        gc_percent.append(float(countG+countC)//float(countC+countG+countA+countT))
                    except (TypeError, ZeroDivisionError) as e:
                        gc_percent.append(None)
                        #don't log error because this is a pretty common error
                        pass

            #avg read length; need calculate, can come from "Run" or "Statistics" heading
            try:
                #have to account for whether it's paired or single to calculate avg read length (bases/reads will be double the actual avg read count if it's paired)
                avg_read_length.append(float(run.get("total_bases"))//(float(run.find("Run").get("spot_count"))+float(run.find("Run").get("spot_count_mates"))))
            except (TypeError, AttributeError, ValueError, ZeroDivisionError) as e: #if one of these values doesn't exist (TypeError), or "Run" tag doesn't exist (AttributeError), or string value that can't be coerced to float (ValueError), try getting it from "Statistics" heading;
                try:
                    avg_read_length.append(float(run.get("total_bases"))//(float(run.find("Statistics").get("nreads"))*float(run.find("Statistics").get("nspots"))))
                except (TypeError, AttributeError, ValueError, ZeroDivisionError) as e:
                    try: #if statistics doesn't work, try dividing total bases by total reads and dividing by 2 if paired
                        if layout=='paired':
                            avg_read_length.append(float(run.get("total_bases"))//(float(run.get("total_spots"))*2))
                        elif layout=='single':
                            avg_read_length.append(float(run.get("total_bases"))//(float(run.get("total_spots"))))
                    except (NameError,TypeError,AttributeError, ValueError, ZeroDivisionError) as e:
                        avg_read_length.append(None)
                        if e.__class__.__name__=='TypeError': #don't log typeerror because really common to be missing values
                            pass
                        else:
                            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg=str(e.__class__.__name__)+"run "+str(run_id)+" avg_read_length",function="get_srx_metadata",date_scraped=datetime.now())
                            db.session.add(errorToWrite)
                            db.session.commit()
                            pass
            #quality count - need get from Run tag if exists
            qual_count = {}
            try:
                qual_list = run.find("Run").find("QualityCount").findall("Quality")
            except AttributeError:
                qual_list = []
            for qual in qual_list:
                try:
                    qual_count[qual.get("value")] = int(qual.get("count"))
                except (TypeError,ValueError) as e:
                    pass
            if (qual_count == {}):
                read_quality_counts.append(None)
            else:
                qual_count = json.dumps(qual_count) # replaced str() coercion with json dump to string for db
                read_quality_counts.append(qual_count)

        if len(total_num_reads)>0:
            max_index = total_num_reads.index(max(total_num_reads))
        else:
            max_index = None

        #log every run scraped to its own rdict entry
        srx_uids = [srx_uid]*len(run_ids)
        n = len(run_ids)
        if all(len(x) == n for x in [srx_uids,run_ids,total_num_reads,total_num_bases,download_size,avg_read_length,baseA_count,baseC_count,baseG_count,baseT_count,baseN_count,gc_percent,read_quality_counts]):
            values = zip(srx_uids,run_ids,total_num_reads,total_num_bases,download_size,avg_read_length,baseA_count,baseC_count,baseG_count,baseT_count,baseN_count,gc_percent,read_quality_counts)
            keys = ['db_source_uid','run_id','library_reads_sequenced','total_num_bases','download_size','avg_read_length','baseA_count','baseC_count','baseG_count','baseT_count','baseN_count','gc_percent','run_quality_counts']
            for value in values:
                #insert into to rdict with key of run_id
                rdict[value[1]] = dict(zip(keys,value))
        else:
            errorToWrite = ScrapeError(uid=str(srx_uid),error_msg="run lists of different lengths while adding to rdict",function="get_srx_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        #log run_ids for writing runs to db later
        srx_dict['run_ids'] = run_ids
        if max_index is not None:
            #log best run (max total_num_reads) to srx data
            srx_dict['run_ids_maxrun'] = run_ids[max_index]
            srx_dict['library_reads_sequenced_maxrun'] = total_num_reads[max_index]
            srx_dict['total_num_bases_maxrun'] = total_num_bases[max_index]
            srx_dict['download_size_maxrun'] = download_size[max_index]
            srx_dict['avg_read_length_maxrun'] = avg_read_length[max_index]
            srx_dict['baseA_count_maxrun'] = baseA_count[max_index]
            srx_dict['baseC_count_maxrun'] = baseC_count[max_index]
            srx_dict['baseG_count_maxrun'] = baseG_count[max_index]
            srx_dict['baseT_count_maxrun'] = baseT_count[max_index]
            srx_dict['baseN_count_maxrun'] = baseN_count[max_index]
            srx_dict['gc_percent_maxrun'] = gc_percent[max_index]
            srx_dict['run_quality_counts_maxrun'] = read_quality_counts[max_index]

        #insert srx data into sdict with srx_uid as key
        sdict[srx_uid] = srx_dict

    print "...done scraping srx metadata in %s" % (datetime.now()-s_scrape_time)

    return sdict, rdict


#takes list of SRX UIDs to query (batch_uid_list), and sdict into which to insert link uids; return sdict with 'biosample_uid' and 'pubmed_uids'; and link dict with lists of biosample_uids, pubmed_uids to scrape
def get_links(batch_uid_list, sdict):
    elink_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=sra&db=biosample,pubmed&tool=metaseq&email=metaseekcloud%40gmail.com'
    for key in batch_uid_list:
        #this makes url with end &id=###&id=###&id=### - returns a set of links in order of sra uids
        elink_url = elink_url+'&id='+str(key)
    #run api request and parse xml
    print "...sending elink request and parsing XML..."
    e_parse_time = datetime.now()
    link_xml = geturl_with_retry(MaxRetry=5,url=elink_url)

    try: #sometimes the url is parsed with lxml but is an error xml output from eutilities; this step fails in that case
        linksets = link_xml.findall("LinkSet")
    except Exception:
        errorToWrite = ScrapeError(uid="url",error_msg="eutilities connection error",function="get_links",date_scraped=datetime.now())
        db.session.add(errorToWrite)
        db.session.commit()
        raise EutilitiesConnectionError('eutilities connection error')

    print "......parsing done in %s" % (datetime.now()-e_parse_time)

    print "...scraping links..."
    e_scrape_time = datetime.now()
    #scrape elink info
    #note if there's no biosample link, <LinkSetDb> with <DbTo>=='biosample' just won't exist
    biosample_uids = []
    pubmed_uids = []

    for linkset in linksets:
        srx_uid = linkset.find("IdList").findtext("Id")
        #links from each target db will be in a tab called "LinkSetDb"
        if len(linkset.findall("LinkSetDb"))>0:
            for link in linkset.findall("LinkSetDb"):
                id_set = []
                if link.findtext("DbTo")=='biosample':
                    #for all Links, get Ids
                    for uid in link.findall("Link"):
                        id_set.append(int(uid.findtext("Id")))
                    biosample_uids.extend(id_set)
                    sdict[srx_uid]['biosample_uid'] = id_set
                elif link.findtext("DbTo")=='pubmed':
                    for uid in link.findall("Link"):
                        id_set.append(int(uid.findtext("Id")))
                    pubmed_uids.extend(id_set)
                    sdict[srx_uid]['pubmed_uids'] = id_set

    biosample_uids = list(set(biosample_uids))
    pubmed_uids = list(set(pubmed_uids))
    print "...done scraping links in %s" % (datetime.now()-e_scrape_time)

    linkdict = {'biosample_uids':biosample_uids,'pubmed_uids':pubmed_uids}
    print "......number of biosamples to scrape: %s" % len(linkdict['biosample_uids'])
    print "......number of pubmeds to scrape: %s" % len(linkdict['pubmed_uids'])

    return sdict,linkdict

def get_biosample_metadata(batch_uid_list,bdict):
    #some stuff already captured with SRA - get again though in case biosample hasn't imported into SRA accession yet
    #biosample_id, sample_title, ncbi_taxon_id, taxon_scientific_name, sample_description,
    #publication_date, Models, Package, and Attributes
    print "...Querying API and parsing biosample XML..."
    b_parse_time = datetime.now()
    biosample_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=biosample&tool=metaseq&email=metaseekcloud%40gmail.com&id='+str(batch_uid_list)[1:-1]
    bio_xml = geturl_with_retry(MaxRetry=5,url=biosample_url)
    try:
        biosamples = bio_xml.findall("BioSample")
    except Exception:
        errorToWrite = ScrapeError(uid="url",error_msg="eutilities connection error",function="get_biosample_metadata",date_scraped=datetime.now())
        db.session.add(errorToWrite)
        db.session.commit()
        raise EutilitiesConnectionError('eutilities connection error')

    print "...parsing done for %s biosamples in %s" % (len(batch_uid_list),(datetime.now()-b_parse_time))
    print "...scraping biosample metadata..."
    b_scrape_time = datetime.now()

    for which,biosample in enumerate(biosamples):
        bio_dict = {}
        try: #if biosample doesn't record biosample uid, not going to be able to merge with sdict; so skip
            if biosample.get("id") is not None:
                bio_id = biosample.get("id")
            else:
                raise AttributeError('no uid attribute in biosample')
        except AttributeError:
            errorToWrite = ScrapeError(uid="url",error_msg="AttributeError couldnt find biosample id which "+str(which),function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            continue
        bio_dict['biosample_uid'] = bio_id
        bio_dict['biosample_link'] = "https://www.ncbi.nlm.nih.gov/biosample/"+str(bio_id)
        #biosample_id
        if biosample.get("accession") is not None: #won't error if doesn't exist
            bio_dict['biosample_id'] = biosample.get("accession")
        #sample_title
        try:
            if biosample.find("Description").findtext("Title") is not None: #don't want to record as None in case this already exists in srx accession but is none in biosample
                bio_dict['sample_title'] = biosample.find("Description").findtext("Title")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg="AttributeError sample_title",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        #ncbi_taxon_id
        try:
            if biosample.find("Description").find("Organism").get("taxonomy_id") is not None:
                bio_dict['ncbi_taxon_id'] = biosample.find("Description").find("Organism").get("taxonomy_id")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg="AttributeError ncbi_taxon_id",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        #taxon_scientific_name
        try:
            if biosample.find("Description").find("Organism").get("taxonomy_name") is not None:
                bio_dict['taxon_scientific_name'] = biosample.find("Description").find("Organism").get("taxonomy_name")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg="AttributeError taxon_scientific_name",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        #sample_description
        try:
            if biosample.find("Description").find("Comment") is not None:
                if biosample.find("Description").find("Comment").findtext("Paragraph") is not None:
                    bio_dict['sample_description'] = biosample.find("Description").find("Comment").findtext("Paragraph")
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg="AttributeError sample_description",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        #publication date
        try:
            bio_dict['metadata_publication_date'] = datetime.strptime(biosample.get('publication_date'), '%Y-%m-%dT%H:%M:%S.%f')
        except (TypeError,ValueError) as e: #if can't parse datetime (ValueError) or publication_date is none (TypeError)
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg=str(e.__class__._name__)+" metadata_publication_date",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass
        #if Package exists, probably don't need Models (but get them anyway); from package/models will parse investigation_type and env_package
        if biosample.findtext("Package") is not None:
            bio_dict['biosample_package'] = biosample.findtext("Package")
        try:
            models = ''
            for model in biosample.find("Models").findall("Model"):
                models = models + model.text + ', '
            bio_dict['biosample_models'] = models[:-2] # remove trailing comma and space
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg="biosample_models",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        #Attributes - loop through attributes; save all as dict in single column (parse later)
        try:
            attr = {}
            for attribute in biosample.find("Attributes").findall("Attribute"):
                try:
                    attr_value = attribute.text
                    if attribute.get("harmonized_name") is not None:
                        attr[attribute.get("harmonized_name")] = attr_value
                    elif attribute.get("attribute_name") is not None:
                        attr[attribute.get("attribute_name")] = attr_value
                except AttributeError:
                    errorToWrite = ScrapeError(uid=str(bio_id),error_msg="AttributeError sample_attribute",function="get_biosample_metadata",date_scraped=datetime.now())
                    db.session.add(errorToWrite)
                    db.session.commit()
                    pass
            bio_dict['sample_attributes'] = attr
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(bio_id),error_msg="AttributeError sample_attributes",function="get_biosample_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        bdict[bio_id] = bio_dict

    print "...done scraping biosample metadata in %s" % (datetime.now()-b_scrape_time)
    return bdict


def get_pubmed_metadata(batch_uid_list,pdict):
    print "...Querying API and parsing XML..."
    p_parse_time = datetime.now()
    pub_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&tool=metaseq&email=metaseekcloud%40gmail.com&id='+str(batch_uid_list)[1:-1]
    pub_xml = geturl_with_retry(MaxRetry=5,url=pub_url)

    try:
        pubmeds = pub_xml.findall("DocSum")
    except Exception:
        errorToWrite = ScrapeError(uid="url",error_msg="eutilities connection error",function="get_pubmed_metadata",date_scraped=datetime.now())
        db.session.add(errorToWrite)
        db.session.commit()
        raise EutilitiesConnectionError('eutilities connection error')

    print "......parsing done for %s pubmeds in %s" % (len(batch_uid_list),(datetime.now()-p_parse_time))
    print "...scraping pubmed metadata..."
    p_scrape_time = datetime.now()

    for which,pubmed in enumerate(pubmeds):
        pub_dict = {}
        try: #if pubmed doesn't pubmed uid (it should), not going to be able to merge with sdict; so skip
            if pubmed.findtext("Id") is not None:
                pub_id = pubmed.findtext("Id")
            else:
                raise AttributeError('no uid attribute in pubmed')
        except AttributeError:
            errorToWrite = ScrapeError(uid="uid",error_msg="AttributeError couldnt find pubmed id which "+str(which),function="get_pubmed_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            continue

        pub_dict['pubmed_uid'] = pub_id
        pub_dict['pubmed_link'] = "https://www.ncbi.nlm.nih.gov/pubmed/"+str(pub_id)

        try:
            pub_dict['pub_publication_date'] = datetime.strptime(pubmed.find("Item[@Name='PubDate']").text,"%Y %b %d")
        except (AttributeError,ValueError) as e: #if can't find attrib (attributeerror) or can't parse datetime (valueerror)
            try:
                pub_dict['pub_publication_date'] = datetime.strptime(pubmed.find("Item[@Name='PubDate']").text,"%Y %b")
            except (AttributeError,ValueError) as e:
                try:
                    pub_dict['pub_publication_date'] = datetime.strptime(pubmed.find("Item[@Name='PubDate']").text,"%Y")
                except (AttributeError,ValueError) as e:
                    try: #e.g. "2010 Jan-Feb" is common, just take first month
                        pub_dict['pub_publication_date'] = datetime.strptime(str(pubmed.find("Item[@Name='PubDate']").text)[0:8],"%Y %b")
                    except (AttributeError,ValueError) as e:
                        ##TODO: flag error if is ValueError; is non-empty but can't parse (2010 Jan-Feb is common format, can get year
                        errorToWrite = ScrapeError(uid=str(pub_id),error_msg=str(e.__class__.__name__)+" pub_publication_date",function="get_pubmed_metadata",date_scraped=datetime.now())
                        db.session.add(errorToWrite)
                        db.session.commit()
                        pass

        try:
            authors = ''
            for author in pubmed.find("Item[@Name='AuthorList']").findall("Item[@Name='Author']"):
                authors = authors + author.text + ', '
            pub_dict['pub_authors'] = authors[:-2] # remove trailing comma and space
        except AttributeError:
            errorToWrite = ScrapeError(uid=str(pub_id),error_msg="AttributeError pub_authors",function="get_pubmed_metadata",date_scraped=datetime.now())
            db.session.add(errorToWrite)
            db.session.commit()
            pass

        if pubmed.findtext("Item[@Name='Title']") is not None: #if doesn't exist is just None, doesn't give attributeerror
            pub_dict['pub_title'] = pubmed.findtext("Item[@Name='Title']")
        if pubmed.findtext("Item[@Name='Volume']") is not None:
            pub_dict['pub_volume'] = pubmed.findtext("Item[@Name='Volume']")
        if pubmed.findtext("Item[@Name='Issue']") is not None:
            pub_dict['pub_issue'] = pubmed.findtext("Item[@Name='Issue']")
        if pubmed.findtext("Item[@Name='Pages']") is not None:
            pub_dict['pub_pages'] = pubmed.findtext("Item[@Name='Pages']")
        if pubmed.findtext("Item[@Name='Source']") is not None:
            pub_dict['pub_journal'] = pubmed.findtext("Item[@Name='Source']")
        if pubmed.findtext("Item[@Name='DOI']") is not None:
            pub_dict['pub_doi'] = pubmed.findtext("Item[@Name='DOI']")

        pdict[pub_id] = pub_dict

    print "...done scraping pubmed metadata in %s" % (datetime.now()-p_scrape_time)

    return pdict

###this fn is no longer used because nuccore_link field not being used, keeping just in case want it in future###
def get_nuccore_metadata(batch_uid_list,ndict):
    print "...scraping nuccore metadata..."
    n_scrape_time = datetime.now()

    for which,nuccore in enumerate(batch_uid_list):
        nuc_dict = {}

        nuc_id = str(nuccore)
        nuc_dict['nuccore_uid'] = nuc_id
        nuc_dict['nuccore_link'] = 'https://www.ncbi.nlm.nih.gov/nuccore/'+nuc_id

        ndict[nuc_id] = nuc_dict

    print "...done scraping nuccore metadata in %s" % (datetime.now()-n_scrape_time)

    return ndict


def merge_scrapes(sdict,bdict,pdict):
    for srx in sdict.keys():
        if 'pubmed_uids' in sdict[srx].keys():
            #append pubmed metadata values to list metadata values for that field in sdict[srx] (if multiple pubmeds, e.g., for each field have list value for all pubmeds, like with run stuff)
            for pub in sdict[srx]['pubmed_uids']:
                pub = str(pub)
                if pub in pdict.keys():
                    ##TODO: error flag if a row has a value in pubmed_uids but doesn't have anything in any of the pubmed_fields
                    #don't need pubmed_uid since already there
                    pubmed_fields = ['pubmed_link','pub_publication_date','pub_authors','pub_title','pub_volume','pub_issue','pub_pages','pub_journal','pub_doi']
                    for pubmed_field in pubmed_fields:
                        if pubmed_field in pdict[pub].keys():
                            if pubmed_field in sdict[srx].keys(): #if field already in sdict[srx], append new value to existing list
                                sdict[srx][pubmed_field].append(pdict[pub][pubmed_field])
                            else: #otherwise add new field with list value (length of one)
                                sdict[srx][pubmed_field] = [pdict[pub][pubmed_field]]

        if 'biosample_uid' in sdict[srx].keys():
            #add biosample metadata fields and values to sdict[srx]
            try:
                if len(sdict[srx]['biosample_uid'])>1:
                    sdict[srx]['biosample_uid'] = None #might be really long string so change to none
                    raise MultipleBiosampleError
            except MultipleBiosampleError:
                errorToWrite = ScrapeError(uid=str(srx),error_msg="MultipleBiosampleError",function="merge_scrapes",date_scraped=datetime.now())
                db.session.add(errorToWrite)
                db.session.commit()
                continue

            if len(sdict[srx]['biosample_uid'])==1:
                bio = str(sdict[srx]['biosample_uid'][0])
                if bio in bdict.keys(): #if bio not in bdict keys, why isn't it? biosample efetch doesn't exist yet for link that was found? biosample uid wasn't in efetch? eutilitiesconnection error during biosample scrape?
                    ##TODO: error flag if a row has a value in biosample_uid but doesn't have anything in any of the biosample_fields
                    #fields from biosample scrape need to add; don't need biosample_uid since already there
                    biosample_fields = ['biosample_link','metadata_publication_date','biosample_package','biosample_models','sample_attributes','biosample_id', 'sample_title', 'ncbi_taxon_id', 'taxon_scientific_name', 'sample_description']
                    for biosample_field in biosample_fields:
                        if biosample_field in bdict[bio].keys():
                            sdict[srx][biosample_field] = bdict[bio][biosample_field]

    return sdict


def extract_and_merge_mixs_fields(sdict, fieldname, rules_json):
    #field e.g. 'sample_attributes'; sdict should be dict of dicts
    #read in rules from json
    with open(rules_json) as json_rules:
        rules = json.load(json_rules)
        json_rules.close()

    for srx in sdict.keys():
        if fieldname in sdict[srx].keys():
            for rule_set in rules.keys():
                #if rule_set is already an srx field with a value (e.g. sequencing_method, taxon_scientific_name), keep the old value and don't replace
                if rule_set in sdict[srx][fieldname].keys() and sdict[srx][fieldname][rule_set] is not None:
                    pass
                #find which redundant fields in rule set exist in sample_attributes
                matches = [x for x in rules[rule_set] if x in sdict[srx][fieldname].keys()]
                if len(matches)>0:
                    #pick replacement as lowest index (highest priority) field ##**MAKE SURE YOU ENTER YOUR RULE SET LIST IN ORDER OF PRIORITY IN THE JSON FILE**##
                    replacement = rules[rule_set][min([rules[rule_set].index(j) for j in matches])]
                    #add column (key:value field) to bio_dict with appropriate MIxS key field
                    sdict[srx][rule_set] = sdict[srx][fieldname][replacement]

    return sdict

def extract_metaseek_power_fields(sdict, srx, manual_rules, tree_rules, investigation_model, model_features):
    '''
    extracting values for metaseek_investigation_type, metaseek_investigation_type_P, metaseek_mixs_specification, metaseek_mixs_specification_P, metaseek_env_package, metaseek_sequencing_method
    using manual parsing, manual parsing from other fields ("manual tree"), or modeling
    '''

    cats = model_features['investigation_type']['columns']
    featcols = ['library_source','library_strategy','library_screening_strategy','study_type']

    #investigation_type
    #manual tree parse
    tree_investigation_rules = tree_rules['investigation_type']
    if 'biosample_package' in sdict[srx].keys():
        if sdict[srx]['biosample_package'] in tree_investigation_rules['biosample_package'].keys():
            metaseek_investigation_type = tree_investigation_rules['biosample_package'][sdict[srx]['biosample_package']]
            metaseek_investigation_type_P = 1.0
    #if can't get manual tree parse, try manual
    try:
        metaseek_investigation_type
    except NameError:
        #manual parse
        investigation_rules = manual_rules['investigation_type']
        if 'investigation_type' in sdict[srx].keys():
            if sdict[srx]['investigation_type'] in investigation_rules.keys():
                metaseek_investigation_type = investigation_rules[sdict[srx]['investigation_type']]
                metaseek_investigation_type_P = 1.0
    #if still can't
    try:
        metaseek_investigation_type
    except NameError:
        #extract one-hot encoded features
        features = {k:sdict[srx][k] for k in featcols if k in sdict[srx].keys()}
        features.update({k:None for k in featcols if k not in sdict[srx].keys()})
        dummies = pd.get_dummies(pd.DataFrame(pd.Series(features)).T)
        newdummies = dummies.reindex(columns=cats).fillna(0)
        #make predictions
        metaseek_investigation_type = investigation_model.predict(newdummies)[0]
        metaseek_investigation_type_P = np.max(investigation_model.predict_proba(newdummies), axis=1)[0]

    #assign investigation_type to sdict[srx]
    sdict[srx]['metaseek_investigation_type'] = metaseek_investigation_type
    sdict[srx]['metaseek_investigation_type_P'] = float(metaseek_investigation_type_P)

    #mixs specification - is derived from investigation_type
    mixs_conversion = {"bacteria_archaea":"MIGS", "eukaryote":"MIGS", "virus":"MIGS", "plasmid":"MIGS", "organelle":"MIGS",
                       "metagenome":"MIMS", "mimarks-culture":"MIMARKS", "mimarks-survey":"MIMARKS"}
    metaseek_mixs_specification = mixs_conversion[metaseek_investigation_type]
    metaseek_mixs_specification_P = metaseek_investigation_type_P
    sdict[srx]['metaseek_mixs_specification'] = metaseek_mixs_specification
    sdict[srx]['metaseek_mixs_specification_P'] = float(metaseek_mixs_specification_P)

    #metaseek_env_package - tree parsing and manual parsing
    #manual tree parse
    tree_env_rules = tree_rules['env_package']
    if 'biosample_package' in sdict[srx].keys():
        if sdict[srx]['biosample_package'] in tree_env_rules['biosample_package'].keys():
            metaseek_env_package = tree_env_rules['biosample_package'][sdict[srx]['biosample_package']]
    #if can't, try manual parse
    try:
        metaseek_env_package
    except NameError:
        env_rules = manual_rules['env_package']
        if 'env_package' in sdict[srx].keys():
            if sdict[srx]['env_package'] in env_rules.keys():
                metaseek_env_package = env_rules[sdict[srx]['env_package']]
                sdict[srx]['metaseek_env_package'] = metaseek_env_package

    #metaseek_sequencing_method - manual parsing only
    seq_meth_rules = manual_rules['sequencing_method']
    if 'sequencing_method' in sdict[srx].keys():
        if sdict[srx]['sequencing_method'] in seq_meth_rules.keys():
            metaseek_sequencing_method = seq_meth_rules[sdict[srx]['sequencing_method']]
            sdict[srx]['metaseek_sequencing_method'] = metaseek_sequencing_method
