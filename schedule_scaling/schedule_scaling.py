""" Collecting Deployments configured for Scaling """
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


def get_resource_to_scale(resource_type="deployment"):
    '''
    Getting the resource configured for schedule scaling...
    '''
    if resource_type not in ['deployment', 'hpa']:
        logging.error('Invalid resource_type')
        return

    api = get_kube_api()
    resources = []
    scaling_dict = {}
    for namespace in list(pykube.Namespace.objects(api)):
        namespace = str(namespace)

        if resource_type == 'deployment':
            resource_list = pykube.Deployment.objects(api).filter(namespace=namespace)
        else:
            resource_list = pykube.HorizontalPodAutoscaler.objects(api).filter(namespace=namespace)

        for resource in resource_list:
            annotations = resource.metadata.get('annotations', {})
            f_resource = str(namespace + '/' + str(resource))

            schedule_actions = parse_content(annotations.get('kube-schedule-scaler/schedule-actions', None), f_resource)

            if schedule_actions is None or len(schedule_actions) == 0:
                continue

            resources.append([resource.metadata['name']])
            scaling_dict[f_resource] = schedule_actions
    if not resources:
        logging.info('No {} is configured for scheduled scaling'.format(resource_type))

    return scaling_dict


def resource_job_creator(resource_type='deployment'):
    """ Create CronJobs for configured resources """

    if resource_type not in ['deployment', 'hpa']:
        logging.error('Invalid resource_type')
        return

    resources__to_scale = get_resource_to_scale(resource_type)
    print("{} collected for scaling: ".format(resource_type))
    for resource_name, schedules in resources__to_scale.items():
        resource = resource_name.split("/")[1]
        namespace = resource_name.split("/")[0]
        for n in range(len(schedules)):
            schedules_n = schedules[n]
            replicas = schedules_n.get('replicas', None)
            minReplicas = schedules_n.get('minReplicas', None)
            maxReplicas = schedules_n.get('maxReplicas', None)
            schedule = schedules_n.get('schedule', None)
            print("%s: %s, Namespace: %s, Replicas: %s, MinReplicas: %s, MaxReplicas: %s, Schedule: %s"
                  % (resource_type, resource, namespace, replicas, minReplicas, maxReplicas, schedule))

            template_file = '/root/schedule_scaling/templates/{}-script.py'.format(resource_type)

            with open(template_file, 'r') as script:
                script = script.read()
            resource_script = script % {
                'namespace': namespace,
                'name': resource,
                'replicas': replicas,
                'minReplicas': minReplicas,
                'maxReplicas': maxReplicas,
                'time': EXECUTION_TIME,
            }
            i = 0
            while os.path.exists("/tmp/scaling_jobs/%s-%s-%s.py" % (resource_type, resource, i)):
                i += 1
            script_creator = open("/tmp/scaling_jobs/%s-%s-%s.py" % (resource_type, resource, i), "w")
            script_creator.write(resource_script)
            script_creator.close()
            cmd = ['. /root/.profile ; /usr/bin/python', script_creator.name,
                   '2>&1 | tee -a /tmp/scale_activities.log']
            cmd = ' '.join(map(str, cmd))
            job = crontab_instance.new(command=cmd)
            try:
                job.setall(schedule)
                job.set_comment("Scheduling_Jobs")
            except Exception:
                print('%s: %s has syntax error in the schedule' % (resource_type, resource))
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
    resource_job_creator('deployment')
    resource_job_creator('hpa')
    commit()
