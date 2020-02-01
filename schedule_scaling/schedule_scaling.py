""" Collecting HPAs configured for Scaling """
import os
import pathlib
import json
import logging
import shutil
import pykube
import re
import urllib.request
import boto3
from crontab import CronTab

EXECUTION_TIME = 'datetime.datetime.now().strftime("%d-%m-%Y %H:%M UTC")'
crontab_instance = CronTab(user="root")

def create_job_directory():
    """ This directory will hold the temp python scripts to execute the scaling jobs """
    temp__dir = '/tmp/scaling_jobs'
    if os.path.isdir(temp__dir):
        shutil.rmtree(temp__dir)
    pathlib.Path(temp__dir).mkdir(parents=True, exist_ok=True)


def clear_cron():
    """ This is needed so that if any one removes his scaling action
          it should not be trigger again """
    crontab_instance.remove_all(comment="Scheduling_Jobs")

def commit():
    try:
        crontab_instance.write()
    except Exception as e:
        print("An exception has been raised while trying to commit the crontab changes")
        print(e)

def get_kube_api():
    """ Initiating the API from Service Account or when running locally from ~/.kube/config """
    try:
        config = pykube.KubeConfig.from_service_account()
    except FileNotFoundError:
        # local testing
        config = pykube.KubeConfig.from_file(os.path.expanduser('~/.kube/config'))
    api = pykube.HTTPClient(config)
    return api


def hpas_to_scale():
    '''
    Getting the HPAs configured for schedule scaling...
    '''
    api = get_kube_api()
    hpa_list = []
    scaling_dict = {}
    for namespace in list(pykube.Namespace.objects(api)):
        namespace = str(namespace)
        for hpa in pykube.HorizontalPodAutoscaler.objects(api).filter(namespace=namespace):
            annotations = hpa.metadata.get('annotations', {})
            f_hpa = str(namespace + '/' + str(hpa))

            schedule_actions = parse_content(annotations.get('kube-schedule-scaler/schedule-actions', None), f_hpa)

            if schedule_actions is None or len(schedule_actions) == 0:
                continue

            hpa_list.append([hpa.metadata['name']])
            scaling_dict[f_hpa] = {
                'hpa': str(hpa),
                'schedule_actions': schedule_actions,
                'deployment': hpa.obj['spec']['scaleTargetRef']['name'],
                'namespace': namespace,
            }
    if not hpa_list:
        logging.info('No hpa is configured for schedule scaling')

    return scaling_dict


def hpa_job_creator():
    """ Create CronJobs for configured HPAs """

    hpas__to_scale = hpas_to_scale()
    print("HPAs collected for scaling: ")
    for namespace_hpa, hpa_config in hpas__to_scale.items():
        hpa = hpa_config['hpa']
        namespace = hpa_config['namespace']
        deployment = hpa_config['deployment']
        schedules = hpa_config['schedule_actions']
        for n in range(len(schedules)):
            schedules_n = schedules[n]
            replicas = schedules_n.get('replicas', None)
            minReplicas = schedules_n.get('minReplicas', None)
            maxReplicas = schedules_n.get('maxReplicas', None)
            schedule = schedules_n.get('schedule', None)
            print("HPA: %s, Namespace: %s, Replicas: %s, MinReplicas: %s, MaxReplicas: %s, Schedule: %s"
                  % (hpa, namespace, replicas, minReplicas, maxReplicas, schedule))

            with open("/root/schedule_scaling/templates/hpa-script.py", 'r') as script:
                script = script.read()
            hpa_script = script % {
                'namespace': namespace,
                'name': hpa,
                'deployment_name': deployment,
                'replicas': replicas,
                'minReplicas': minReplicas,
                'maxReplicas': maxReplicas,
                'time': EXECUTION_TIME,
            }
            i = 0
            while os.path.exists("/tmp/scaling_jobs/%s-%s.py" % (hpa, i)):
                i += 1
            script_creator = open("/tmp/scaling_jobs/%s-%s.py" % (hpa, i), "w")
            script_creator.write(hpa_script)
            script_creator.close()
            cmd = ['. /root/.profile ; /usr/bin/python', script_creator.name,
                   '2>&1 | tee -a /tmp/scale_activities.log']
            cmd = ' '.join(map(str, cmd))
            job = crontab_instance.new(command=cmd)
            try:
                job.setall(schedule)
                job.set_comment("Scheduling_Jobs")
            except Exception:
                print('HPA: %s has syntax error in the schedule' % (hpa))
                job.delete()

def parse_content(content, identifier):
    if content == None:
        return []

    if is_valid_s3_url(content):
        schedules = fetch_schedule_actions_s3(content)

        if schedules == None:
            return []

        return parse_schedules(schedules, identifier)

    if is_valid_url(content):
        schedules = fetch_schedule_actions_from_url(content)

        if schedules == None:
            return []

        return parse_schedules(schedules, identifier)

    return parse_schedules(content, identifier)

def is_valid_url(url):
    return re.search('^(https?)://(\\S+)\.(\\S{2,}?)(/\\S+)?$', url, re.I) != None

def is_valid_s3_url(url):
    return parse_s3_url(url) != None

def parse_s3_url(url):
    match = re.search('^s3://(\\S+?)/(\\S+)$', url, re.I)

    if match == None:
        return None

    return {
        'Bucket': match.group(1),
        'Key': match.group(2)
    }

def fetch_schedule_actions_s3(url):
    source = parse_s3_url(url)

    print(source)

    s3 = boto3.client('s3')
    try:
        element = s3.get_object(**source)
    except:
        print('Couldn\'t read %s' % (url))
        return '[]'

    return element['Body'].read().decode('utf-8')

def fetch_schedule_actions_from_url(url):
    request = urllib.request.urlopen(url)
    try:
        content = request.read().decode('utf-8')
    except:
        content = None
    finally:
        request.close()

    return content

def parse_schedules(schedules, identifier):
    try:
        return json.loads(schedules)
    except Exception as err:
        print('%s - Error in parsing JSON %s with error' % (identifier, schedules), err)
        return []

if __name__ == '__main__':
    create_job_directory()
    clear_cron()
    hpa_job_creator()
    commit()
