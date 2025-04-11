"""Kubernetes cleaner implementation for removing unused Kubernetes resources."""

import json
import logging
import inspect
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.k8s")


class KubernetesCleaner(Cleaner):
    """Cleaner for Kubernetes resources."""

    def __init__(self, timeout: int = 30):
        """
        Initialize the Kubernetes cleaner.
        
        Args:
            timeout: Default timeout for kubectl commands in seconds
        """
        self.timeout = timeout
        # 保护资源列表 - 永远不会被删除的资源
        self.protected_namespaces = {
            'kube-system', 'kube-public', 'kube-node-lease',
            'cert-manager', 'istio-system', 'monitoring',
            'ingress-nginx', 'default'
        }
        self.protected_prefixes = {
            'kube-', 'calico-', 'istio-', 'cert-manager-',
            'prometheus-', 'grafana-', 'default-token-'
        }

    @property
    def name(self) -> str:
        return "k8s"

    @property
    def description(self) -> str:
        return "Removes unused Kubernetes resources (pods, replicasets, configmaps, secrets)"

    def display_help(self) -> None:
        """Display detailed help information for the Kubernetes cleaner."""
        help_text = """
Kubernetes Cleaner Help
=======================

The Kubernetes cleaner is a tool to clean unused Kubernetes resources, helping you
reclaim cluster resources and improve performance. It can identify and remove:

1. Completed/Failed Pods - Pods that have finished executing or failed
2. Old ReplicaSets - ReplicaSets no longer managing any pods
3. Unused ConfigMaps - ConfigMaps not mounted by any pods
4. Unused Secrets - Secrets not mounted by any pods or service accounts

USAGE:
    maccleaner clean k8s [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable Kubernetes resources (simulation mode)
    maccleaner clean k8s --dry-run

    # Clean all unused Kubernetes resources older than 30 days
    maccleaner clean k8s

    # Clean unused Kubernetes resources older than 90 days
    maccleaner clean k8s --days 90

IMPORTANT NOTES:
    - The cleaner will only operate on the current Kubernetes context
    - Protected resources (in kube-system, etc.) will never be removed
    - Resources with protected prefixes (kube-, calico-, etc.) will be skipped
    - The cleaner checks for resource references before removing ConfigMaps and Secrets
"""
        print(help_text)

    def check_prerequisites(self) -> bool:
        """Check if kubectl is installed and accessible, and cluster is reachable."""
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Checking kubectl client version...")
        
        client_check = run_command("kubectl version --client", timeout=10)
        if not client_check:
            logger.error(f"[Line {line}] kubectl is not installed or not available in PATH")
            return False
        
        logger.info(f"[Line {line}] kubectl client detected: {client_check[:50]}...")
        logger.info(f"[Line {line}] Checking connection to Kubernetes cluster...")
        
        # 检查集群连接，使用健康检查端点
        cluster_check = run_command("kubectl get --raw /healthz", timeout=15)
        if not cluster_check or cluster_check != "ok":
            logger.error(f"[Line {line}] Unable to connect to Kubernetes cluster: {cluster_check}")
            return False
        
        logger.info(f"[Line {line}] Successfully connected to Kubernetes cluster")
        return True

    def _run_kubectl(self, command: str, timeout: Optional[int] = None) -> Optional[str]:
        """
        Run a kubectl command with timeout and logging.
        
        Args:
            command: The kubectl command to run
            timeout: Command timeout in seconds (overrides default)
            
        Returns:
            Command output or None if the command failed
        """
        line = inspect.currentframe().f_lineno
        actual_timeout = timeout if timeout is not None else self.timeout
        logger.debug(f"[Line {line}] Running kubectl command (timeout: {actual_timeout}s): {command}")
        
        start_time = time.time()
        result = run_command(command, timeout=actual_timeout)
        execution_time = time.time() - start_time
        
        if result is None:
            logger.warning(f"[Line {line}] kubectl command failed or timed out after {execution_time:.2f}s: {command}")
        else:
            logger.debug(f"[Line {line}] kubectl command completed in {execution_time:.2f}s")
            
        return result

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused Kubernetes resources.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of unused resources with metadata
        """
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Searching for unused Kubernetes resources older than {days_threshold} days")
        
        current_context = self._get_current_context()
        if not current_context:
            logger.error(f"[Line {line}] Failed to get current Kubernetes context")
            return []
        
        logger.info(f"[Line {line}] Using Kubernetes context: {current_context}")
        
        # Get all types of resources that can be cleaned
        logger.info(f"[Line {line}] Looking for completed pods...")
        completed_pods = self._get_completed_pods(days_threshold)
        logger.info(f"[Line {line}] Found {len(completed_pods)} completed/failed pods to clean")
        
        logger.info(f"[Line {line}] Looking for old replicasets...")
        old_replicasets = self._get_old_replicasets(days_threshold)
        logger.info(f"[Line {line}] Found {len(old_replicasets)} unused replicasets to clean")
        
        logger.info(f"[Line {line}] Looking for unused configmaps...")
        unused_configmaps = self._get_unused_configmaps(days_threshold)
        logger.info(f"[Line {line}] Found {len(unused_configmaps)} unused configmaps to clean")
        
        logger.info(f"[Line {line}] Looking for unused secrets...")
        unused_secrets = self._get_unused_secrets(days_threshold)
        logger.info(f"[Line {line}] Found {len(unused_secrets)} unused secrets to clean")
        
        # Combine them into a single list with a type field
        cleanable_items = []
        
        for pod in completed_pods:
            pod["type"] = "pod"
            cleanable_items.append(pod)
            
        for rs in old_replicasets:
            rs["type"] = "replicaset"
            cleanable_items.append(rs)
            
        for cm in unused_configmaps:
            cm["type"] = "configmap"
            cleanable_items.append(cm)
            
        for secret in unused_secrets:
            secret["type"] = "secret"
            cleanable_items.append(secret)
            
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Found total of {len(cleanable_items)} Kubernetes resources to clean")
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Kubernetes resource.
        
        Args:
            item: The resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        line = inspect.currentframe().f_lineno
        item_type = item["type"]
        namespace = item["namespace"]
        name = item["name"]
        
        # 安全检查 - 确保我们不会删除受保护的资源
        if namespace in self.protected_namespaces:
            logger.warning(f"[Line {line}] Skipping protected namespace resource: {namespace}/{name}")
            return False
            
        for prefix in self.protected_prefixes:
            if name.startswith(prefix):
                logger.warning(f"[Line {line}] Skipping protected resource: {namespace}/{name}")
                return False
        
        if dry_run:
            logger.debug(f"[Line {line}] [DRY RUN] Would delete {item_type}: {namespace}/{name}")
            return True
        
        # Command format depends on resource type
        if item_type == "pod":
            cmd = f"kubectl delete pod {name} -n {namespace} --grace-period=30"
            logger.info(f"[Line {line}] Deleting pod: {namespace}/{name}")
        elif item_type == "replicaset":
            cmd = f"kubectl delete rs {name} -n {namespace} --grace-period=30"
            logger.info(f"[Line {line}] Deleting replicaset: {namespace}/{name}")
        elif item_type == "configmap":
            cmd = f"kubectl delete configmap {name} -n {namespace}"
            logger.info(f"[Line {line}] Deleting configmap: {namespace}/{name}")
        elif item_type == "secret":
            cmd = f"kubectl delete secret {name} -n {namespace}"
            logger.info(f"[Line {line}] Deleting secret: {namespace}/{name}")
        else:
            logger.error(f"[Line {line}] Unknown Kubernetes resource type: {item_type}")
            return False
        
        result = self._run_kubectl(cmd, timeout=45)
        if result is None:
            logger.error(f"[Line {line}] Failed to delete {item_type}: {namespace}/{name}")
            return False
            
        logger.info(f"[Line {line}] Successfully deleted {item_type}: {namespace}/{name}")
        return True

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert a Kubernetes resource to a string representation.
        
        Args:
            item: The Kubernetes resource
            
        Returns:
            String representation of the resource
        """
        item_type = item["type"]
        name = item["name"]
        namespace = item["namespace"]
        age_days = item.get("age_days", 0)
        
        if item_type == "pod":
            phase = item.get("phase", "Unknown")
            return f"Pod: {namespace}/{name} ({phase}, {age_days} days old)"
        elif item_type == "replicaset":
            return f"ReplicaSet: {namespace}/{name} ({age_days} days old)"
        elif item_type == "configmap":
            return f"ConfigMap: {namespace}/{name} ({age_days} days old)"
        elif item_type == "secret":
            return f"Secret: {namespace}/{name} ({age_days} days old)"
        else:
            return str(item)

    def _get_current_context(self) -> Optional[str]:
        """
        Get the current Kubernetes context.
        
        Returns:
            The current context name, or None if it can't be determined
        """
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Getting current Kubernetes context")
        return self._run_kubectl("kubectl config current-context")

    def _get_completed_pods(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of completed or failed pods older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of old completed/failed pods
        """
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Fetching all pods across all namespaces")
        
        # List completed/failed/succeeded pods in JSON format
        cmd = "kubectl get pods --all-namespaces -o json"
        output = self._run_kubectl(cmd, timeout=60)
        
        if not output:
            logger.warning(f"[Line {line}] No pods found or kubectl command failed")
            return []
        
        try:
            pods_data = json.loads(output)
            all_pods = pods_data.get('items', [])
            logger.debug(f"[Line {line}] Processing {len(all_pods)} pods")
            
            completed_pods = []
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            for pod in all_pods:
                pod_name = pod.get('metadata', {}).get('name', '')
                pod_namespace = pod.get('metadata', {}).get('namespace', '')
                
                # 跳过受保护的命名空间
                if pod_namespace in self.protected_namespaces:
                    logger.debug(f"[Line {line}] Skipping pod in protected namespace: {pod_namespace}/{pod_name}")
                    continue
                    
                # 跳过受保护的资源名
                skip = False
                for prefix in self.protected_prefixes:
                    if pod_name.startswith(prefix):
                        logger.debug(f"[Line {line}] Skipping pod with protected prefix: {pod_namespace}/{pod_name}")
                        skip = True
                        break
                
                if skip:
                    continue
                
                pod_status = pod.get('status', {})
                phase = pod_status.get('phase', '')
                
                # Check if pod is completed or failed
                if phase in ['Succeeded', 'Failed']:
                    # Get age of the pod
                    creation_timestamp = pod.get('metadata', {}).get('creationTimestamp', '')
                    age_days = 0
                    
                    if creation_timestamp:
                        try:
                            # Parse the creation timestamp
                            creation_time = datetime.strptime(creation_timestamp, '%Y-%m-%dT%H:%M:%SZ')
                            age_days = (datetime.now() - creation_time).days
                            
                            # Check if pod is older than threshold 
                            if creation_time < threshold_date:
                                logger.debug(f"[Line {line}] Found old {phase} pod: {pod_namespace}/{pod_name}, age: {age_days} days")
                                completed_pods.append({
                                    'name': pod_name,
                                    'namespace': pod_namespace,
                                    'phase': phase,
                                    'age_days': age_days,
                                    'creation_time': creation_time.strftime('%Y-%m-%d %H:%M:%S')
                                })
                            else:
                                logger.debug(f"[Line {line}] Pod {pod_namespace}/{pod_name} is too recent ({age_days} days)")
                        except ValueError as e:
                            logger.warning(f"[Line {line}] Error parsing pod creation time: {e}")
                            continue
            
            line = inspect.currentframe().f_lineno
            logger.debug(f"[Line {line}] Found {len(completed_pods)} completed/failed pods older than {days_threshold} days")
            return completed_pods
        except json.JSONDecodeError as e:
            logger.error(f"[Line {line}] Error parsing kubectl output: {e}")
            return []

    def _get_old_replicasets(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of old ReplicaSets that are not currently used.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of old unused ReplicaSets
        """
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Fetching all replicasets across all namespaces")
        
        # List all ReplicaSets in JSON format
        cmd = "kubectl get rs --all-namespaces -o json"
        output = self._run_kubectl(cmd, timeout=45)
        
        if not output:
            logger.warning(f"[Line {line}] No replicasets found or kubectl command failed")
            return []
        
        try:
            rs_data = json.loads(output)
            all_rs = rs_data.get('items', [])
            logger.debug(f"[Line {line}] Processing {len(all_rs)} replicasets")
            
            old_replicasets = []
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            for rs in all_rs:
                rs_name = rs.get('metadata', {}).get('name', '')
                rs_namespace = rs.get('metadata', {}).get('namespace', '')
                
                # 跳过受保护的命名空间
                if rs_namespace in self.protected_namespaces:
                    logger.debug(f"[Line {line}] Skipping replicaset in protected namespace: {rs_namespace}/{rs_name}")
                    continue
                
                # 跳过受保护的资源名
                skip = False
                for prefix in self.protected_prefixes:
                    if rs_name.startswith(prefix):
                        logger.debug(f"[Line {line}] Skipping replicaset with protected prefix: {rs_namespace}/{rs_name}")
                        skip = True
                        break
                
                if skip:
                    continue
                
                # Check if ReplicaSet has 0 replicas
                replicas = rs.get('spec', {}).get('replicas', 0)
                status_replicas = rs.get('status', {}).get('replicas', 0)
                
                if replicas == 0 and status_replicas == 0:
                    # Get age of the ReplicaSet
                    creation_timestamp = rs.get('metadata', {}).get('creationTimestamp', '')
                    age_days = 0
                    
                    if creation_timestamp:
                        try:
                            # Parse the creation timestamp
                            creation_time = datetime.strptime(creation_timestamp, '%Y-%m-%dT%H:%M:%SZ')
                            age_days = (datetime.now() - creation_time).days
                            
                            # Only include ReplicaSets older than the threshold
                            if creation_time < threshold_date:
                                logger.debug(f"[Line {line}] Found old replicaset with 0 replicas: {rs_namespace}/{rs_name}, age: {age_days} days")
                                old_replicasets.append({
                                    'name': rs_name,
                                    'namespace': rs_namespace,
                                    'age_days': age_days,
                                    'creation_time': creation_time.strftime('%Y-%m-%d %H:%M:%S')
                                })
                            else:
                                logger.debug(f"[Line {line}] ReplicaSet {rs_namespace}/{rs_name} is too recent ({age_days} days)")
                        except ValueError as e:
                            logger.warning(f"[Line {line}] Error parsing replicaset creation time: {e}")
                            continue
                else:
                    logger.debug(f"[Line {line}] Skipping replicaset {rs_namespace}/{rs_name} with {status_replicas} replicas")
            
            line = inspect.currentframe().f_lineno
            logger.debug(f"[Line {line}] Found {len(old_replicasets)} unused replicasets older than {days_threshold} days")
            return old_replicasets
        except json.JSONDecodeError as e:
            logger.error(f"[Line {line}] Error parsing kubectl output: {e}")
            return []

    def _get_k8s_references(self) -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]]]:
        """
        Get ConfigMaps and Secrets referenced by any Kubernetes resource.
        
        This searches not just for Pods, but also Deployments, StatefulSets,
        DaemonSets, CronJobs, etc. that might reference ConfigMaps or Secrets.
        
        Returns:
            Tuple containing (referenced_configmaps, referenced_secrets)
        """
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Getting ConfigMap and Secret references from Kubernetes resources")
        
        referenced_configmaps = set()
        referenced_secrets = set()
        
        # Resource types to check for ConfigMap/Secret references
        resource_types = [
            "pods", "deployments", "statefulsets", "daemonsets",
            "cronjobs", "jobs", "replicasets"
        ]
        
        for resource_type in resource_types:
            logger.debug(f"[Line {line}] Checking {resource_type} for ConfigMap/Secret references")
            cmd = f"kubectl get {resource_type} --all-namespaces -o json"
            output = self._run_kubectl(cmd, timeout=30)
            
            if not output:
                logger.debug(f"[Line {line}] No {resource_type} found or command failed")
                continue
                
            try:
                resources = json.loads(output)
                
                for resource in resources.get('items', []):
                    namespace = resource.get('metadata', {}).get('namespace', 'default')
                    
                    # Get ConfigMap volumes from pod template spec
                    if resource_type != "pods":
                        # For controllers, check pod template
                        template = resource.get('spec', {}).get('template', {})
                        spec = template.get('spec', {})
                    else:
                        # For pods, check spec directly
                        spec = resource.get('spec', {})
                    
                    # Check volumes for ConfigMap and Secret references
                    for volume in spec.get('volumes', []):
                        if 'configMap' in volume:
                            cm_name = volume.get('configMap', {}).get('name')
                            if cm_name:
                                referenced_configmaps.add((namespace, cm_name))
                                logger.debug(f"[Line {line}] Found ConfigMap reference: {namespace}/{cm_name}")
                        
                        if 'secret' in volume:
                            secret_name = volume.get('secret', {}).get('secretName')
                            if secret_name:
                                referenced_secrets.add((namespace, secret_name))
                                logger.debug(f"[Line {line}] Found Secret reference: {namespace}/{secret_name}")
                    
                    # Check containers for env references
                    for container in spec.get('containers', []) + spec.get('initContainers', []):
                        # Check envFrom
                        for env_from in container.get('envFrom', []):
                            if 'configMapRef' in env_from:
                                cm_name = env_from.get('configMapRef', {}).get('name')
                                if cm_name:
                                    referenced_configmaps.add((namespace, cm_name))
                                    logger.debug(f"[Line {line}] Found ConfigMap reference: {namespace}/{cm_name}")
                            
                            if 'secretRef' in env_from:
                                secret_name = env_from.get('secretRef', {}).get('name')
                                if secret_name:
                                    referenced_secrets.add((namespace, secret_name))
                                    logger.debug(f"[Line {line}] Found Secret reference: {namespace}/{secret_name}")
                        
                        # Check individual env vars
                        for env in container.get('env', []):
                            if 'valueFrom' in env:
                                value_from = env.get('valueFrom', {})
                                
                                if 'configMapKeyRef' in value_from:
                                    cm_name = value_from.get('configMapKeyRef', {}).get('name')
                                    if cm_name:
                                        referenced_configmaps.add((namespace, cm_name))
                                        logger.debug(f"[Line {line}] Found ConfigMap reference: {namespace}/{cm_name}")
                                
                                if 'secretKeyRef' in value_from:
                                    secret_name = value_from.get('secretKeyRef', {}).get('name')
                                    if secret_name:
                                        referenced_secrets.add((namespace, secret_name))
                                        logger.debug(f"[Line {line}] Found Secret reference: {namespace}/{secret_name}")
            
            except json.JSONDecodeError as e:
                logger.error(f"[Line {line}] Error parsing {resource_type} output: {e}")
                continue
        
        logger.debug(f"[Line {line}] Found {len(referenced_configmaps)} referenced ConfigMaps and {len(referenced_secrets)} referenced Secrets")
        return (referenced_configmaps, referenced_secrets)

    def _get_unused_configmaps(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of ConfigMaps not referenced by any resource and older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of unused ConfigMaps
        """
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Fetching all configmaps across all namespaces")
        
        # List all ConfigMaps in JSON format
        cmd = "kubectl get configmaps --all-namespaces -o json"
        cm_output = self._run_kubectl(cmd, timeout=30)
        
        if not cm_output:
            logger.warning(f"[Line {line}] No configmaps found or kubectl command failed")
            return []
        
        # Get referenced ConfigMaps from all resources
        referenced_configmaps, _ = self._get_k8s_references()
        
        try:
            cm_data = json.loads(cm_output)
            all_cms = cm_data.get('items', [])
            logger.debug(f"[Line {line}] Processing {len(all_cms)} configmaps")
            
            # Find ConfigMaps not referenced by any resource
            unused_configmaps = []
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            for cm in all_cms:
                cm_name = cm.get('metadata', {}).get('name', '')
                cm_namespace = cm.get('metadata', {}).get('namespace', '')
                
                # Skip protected namespaces and resources
                if cm_namespace in self.protected_namespaces:
                    logger.debug(f"[Line {line}] Skipping configmap in protected namespace: {cm_namespace}/{cm_name}")
                    continue
                
                skip = False
                for prefix in self.protected_prefixes:
                    if cm_name.startswith(prefix):
                        logger.debug(f"[Line {line}] Skipping configmap with protected prefix: {cm_namespace}/{cm_name}")
                        skip = True
                        break
                
                if skip:
                    continue
                
                # Check if ConfigMap is referenced by any resource
                if (cm_namespace, cm_name) in referenced_configmaps:
                    logger.debug(f"[Line {line}] ConfigMap {cm_namespace}/{cm_name} is in use by some resource")
                    continue
                
                # Get age of the ConfigMap
                creation_timestamp = cm.get('metadata', {}).get('creationTimestamp', '')
                age_days = 0
                
                if creation_timestamp:
                    try:
                        # Parse the creation timestamp
                        creation_time = datetime.strptime(creation_timestamp, '%Y-%m-%dT%H:%M:%SZ')
                        age_days = (datetime.now() - creation_time).days
                        
                        # Only include ConfigMaps older than the threshold
                        if creation_time < threshold_date:
                            logger.debug(f"[Line {line}] Found unused configmap: {cm_namespace}/{cm_name}, age: {age_days} days")
                            unused_configmaps.append({
                                'name': cm_name,
                                'namespace': cm_namespace,
                                'age_days': age_days,
                                'creation_time': creation_time.strftime('%Y-%m-%d %H:%M:%S')
                            })
                        else:
                            logger.debug(f"[Line {line}] ConfigMap {cm_namespace}/{cm_name} is too recent ({age_days} days)")
                    except ValueError as e:
                        logger.warning(f"[Line {line}] Error parsing configmap creation time: {e}")
                        continue
            
            line = inspect.currentframe().f_lineno
            logger.debug(f"[Line {line}] Found {len(unused_configmaps)} unused configmaps older than {days_threshold} days")
            return unused_configmaps
        except json.JSONDecodeError as e:
            logger.error(f"[Line {line}] Error parsing kubectl output: {e}")
            return []

    def _get_unused_secrets(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of Secrets not referenced by any resource and older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of unused Secrets
        """
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Fetching all secrets across all namespaces")
        
        # List all Secrets in JSON format
        cmd = "kubectl get secrets --all-namespaces -o json"
        secret_output = self._run_kubectl(cmd, timeout=30)
        
        if not secret_output:
            logger.warning(f"[Line {line}] No secrets found or kubectl command failed")
            return []
        
        # Get referenced Secrets from all resources
        _, referenced_secrets = self._get_k8s_references()
        
        try:
            secret_data = json.loads(secret_output)
            all_secrets = secret_data.get('items', [])
            logger.debug(f"[Line {line}] Processing {len(all_secrets)} secrets")
            
            # Find Secrets not used by any resource
            unused_secrets = []
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            for secret in all_secrets:
                secret_name = secret.get('metadata', {}).get('name', '')
                secret_namespace = secret.get('metadata', {}).get('namespace', '')
                secret_type = secret.get('type', '')
                
                # Skip system Secrets, service account tokens, and in protected namespaces
                if (secret_namespace in self.protected_namespaces or
                    secret_type == 'kubernetes.io/service-account-token'):
                    logger.debug(f"[Line {line}] Skipping protected secret: {secret_namespace}/{secret_name} (type: {secret_type})")
                    continue
                
                skip = False
                for prefix in self.protected_prefixes:
                    if secret_name.startswith(prefix):
                        logger.debug(f"[Line {line}] Skipping secret with protected prefix: {secret_namespace}/{secret_name}")
                        skip = True
                        break
                
                if skip:
                    continue
                
                # Check if Secret is referenced by any resource
                if (secret_namespace, secret_name) in referenced_secrets:
                    logger.debug(f"[Line {line}] Secret {secret_namespace}/{secret_name} is in use by some resource")
                    continue
                
                # Get age of the Secret
                creation_timestamp = secret.get('metadata', {}).get('creationTimestamp', '')
                age_days = 0
                
                if creation_timestamp:
                    try:
                        # Parse the creation timestamp
                        creation_time = datetime.strptime(creation_timestamp, '%Y-%m-%dT%H:%M:%SZ')
                        age_days = (datetime.now() - creation_time).days
                        
                        # Only include Secrets older than the threshold
                        if creation_time < threshold_date:
                            logger.debug(f"[Line {line}] Found unused secret: {secret_namespace}/{secret_name}, age: {age_days} days")
                            unused_secrets.append({
                                'name': secret_name,
                                'namespace': secret_namespace,
                                'age_days': age_days,
                                'type': secret_type,
                                'creation_time': creation_time.strftime('%Y-%m-%d %H:%M:%S')
                            })
                        else:
                            logger.debug(f"[Line {line}] Secret {secret_namespace}/{secret_name} is too recent ({age_days} days)")
                    except ValueError as e:
                        logger.warning(f"[Line {line}] Error parsing secret creation time: {e}")
                        continue
            
            line = inspect.currentframe().f_lineno
            logger.debug(f"[Line {line}] Found {len(unused_secrets)} unused secrets older than {days_threshold} days")
            return unused_secrets
        except json.JSONDecodeError as e:
            logger.error(f"[Line {line}] Error parsing kubectl output: {e}")
            return []

    def clean(self, days_threshold: int = 30, dry_run: bool = True, args: Optional[List[str]] = None) -> bool:
        """
        Clean unused Kubernetes resources.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            dry_run: If True, only simulate cleaning
            args: Additional command line arguments
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        # Check for help argument
        if args and ('--help' in args or '-h' in args):
            self.display_help()
            return True
            
        # Continue with regular cleaning process
        return super().clean(days_threshold, dry_run)


# Register this cleaner
CLEANER_REGISTRY["k8s"] = KubernetesCleaner 