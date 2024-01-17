import os
import time
import yaml
import jinja2


import boto3

from pathlib import Path
from botocore.config import Config

# AWS_CONFIG_LOCATION_PATH
AWS_AMI="ami-0cd3c7f72edd5b06d"


BOTO3_INSTANCE_STATUS_CODE_RUNNING=16
BOTO3_INSTANCE_STATUS_NAME_RUNNING='running'

AWS_DEVBOX_NAME_PREFIX='vscode_devbox'
AWS_DEFAULT_SSH_PORT='22'
AWS_DEFAULT_USER='ec2-user'

AWS_SSH_KEY_REGISTRY={'aws_cassiopeia':'~/.ssh/aws_cassiopeia.openssh_private'}

SUPPLEMENTAL_CONFIG_FILE_LOCATION_FILE_PATH=Path.home() / ".ssh" / "supplemental_ssh_config_files" / "vscode_config"


def ssh_suppl_config_file(suppl_host_file_full_path, list_of_vm_properties):
    """
    Write a supplemental config file containing the provisioned host information.

    It expect that the ~/.ssh/config contains a 'Include ~/.ssh/supplemental_ssh_config_files/*' statement.

    Input:
        suppl_host_file_full_path:  Path object
        list_of_vm_properties: list of dict
        [  
            {
                alias: string
                public_ip: string
                user: string
                identity_file: string
            }
        ]
    
    Output:
        Only outputs a files. No returned value
    """
    
    if not(isinstance(suppl_host_file_full_path,Path)):
        # YOLO
        suppl_host_file_full_path=Path(suppl_host_file_full_path)
    
    jinja_environment=jinja2.Environment(loader=jinja2.FileSystemLoader("templates/"))
    hostfile_template = jinja_environment.get_template('ssh_config.j2')

    j2_context={
        "list_of_vm":list_of_vm_properties
    }

    rendered_content=hostfile_template.render(j2_context)

    with open(suppl_host_file_full_path, mode='w', encoding='utf-8') as message:
        message.write(rendered_content)

def aws_wait_for_instance_status(ec2_client,ec2_instances, status_code=None, status_name=None, interval_wait=15, max_tries=40):
    """
    Couldn't figure out how to implement this method: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/instance/wait_until_running.html#wait-until-running
    So I am implementing my own with the client
    Input:
        ec2_client: Boto3.Session.Client('ec2) object

        ec2_instances: Dictionnary output of the Boto3.Session.Client('ec2').run_instance() function

        status_code: integer

        status_name: str

        Either status_code or status_name must be defined. If both are define, status_code takes precedence

    Output
        Outputs the filter constructed in this function

    """
    instances_id=list()
    instance_filter=list()
    attempt=0
    status_correct_for_all_instances=True

    if status_code is None and status_name is None:
        raise
    elif status_code is not None:
            key_to_get='Code'
            value_to_compare_to=status_code
    elif status_name is not None:
            key_to_get='Name'
            value_to_compare_to=status_name


    
    for instance in ec2_instances['Instances']:
        instances_id.append(instance['InstanceId'])

   
    instance_filter.append({
            'Name': 'instance-id',
            'Values': instances_id
        })
    
    
    
    while attempt<=max_tries:
        status_correct_for_all_instances=True
        instance_description=ec2_client.describe_instances(Filters=instance_filter)
        for reservation in instance_description['Reservations']:
            for instance in reservation['Instances']:
                status_correct_for_all_instances =status_correct_for_all_instances and instance['State'][key_to_get]==value_to_compare_to

        if status_correct_for_all_instances:
            break

        attempt=attempt+1
        time.sleep(interval_wait)
    
    return instance_filter


def main():
    # os.environ("AWS_SHARED_CREDENTIALS_FILE")="./.aws/credentials"

    # aws_session=boto3.Session()

    molecule_aws_session=boto3.Session(profile_name = 'molecule',
                                       region_name = 'us-east-2',
                                       )


    ec2_client = molecule_aws_session.client('ec2', )

    ec2_instances_created = ec2_client.run_instances(
            ImageId="ami-0cd3c7f72edd5b06d",
            MinCount=2,
            MaxCount=2,
            InstanceType="t2.micro",
            KeyName="aws_cassiopeia",
            SecurityGroupIds=[
                'sg-07dc750bf6a24d612',
            ],
        )
    
    ec2_filters = aws_wait_for_instance_status(ec2_client,ec2_instances_created,status_name=BOTO3_INSTANCE_STATUS_NAME_RUNNING)
    
    instances_descriptions=ec2_client.describe_instances(Filters=ec2_filters)

    aws_vm_properties=list()

    for reservation in instances_descriptions['Reservations']:
        for instance in reservation['Instances']:
            instance_properties=dict()
            
            alias_prefix=AWS_DEVBOX_NAME_PREFIX
            alias_suffix='_'+instance['InstanceId'][-4:]
            instance_name=alias_prefix+alias_suffix

            ec2_client.create_tags(Resources=[instance['InstanceId']],
                                   Tags=[{
                                       'Key':'Name',
                                       'Value':instance_name,
                                  },
                                ])

            instance_properties={'alias':instance_name,
                                 'user':AWS_DEFAULT_USER,
                                 'public_ip':instance['PublicIpAddress'],
                                 'identity_file':AWS_SSH_KEY_REGISTRY.get(instance['KeyName'], "NO_SSH_KEY_IN_REGISTRY_FOR_"+instance['KeyName']),
                                 }
            


            aws_vm_properties.append(instance_properties)

    ssh_suppl_config_file(
        SUPPLEMENTAL_CONFIG_FILE_LOCATION_FILE_PATH,
        aws_vm_properties)


if __name__=="__main__":
    main()
