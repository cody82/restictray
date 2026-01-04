import sys
import asyncio
import json
import logging
import locale
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMainWindow, QTextEdit, 
    QVBoxLayout, QHBoxLayout, QWidget, QTabWidget, QLabel, QListWidget,
    QPushButton, QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox,
    QComboBox, QCheckBox, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QTreeWidget, QTreeWidgetItem, QSplitter
)
from PySide6.QtGui import QIcon, QAction, QColor
from PySide6.QtCore import QTimer, Qt, QTranslator, QLocale, QCoreApplication
from qasync import QEventLoop
from restictray.restic import BackupExecutor
from restictray.storage import Storage, Repository, Job, History
from restictray.scheduler import JobScheduler
from restictray import globals

# Configure logging
#logging.basicConfig(
#    level=logging.DEBUG,
#    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#    handlers=[
#        logging.StreamHandler(sys.stdout)
#    ]
#)
#logger = logging.getLogger(__name__)

executors: list[BackupExecutor] = []

class LoadingDialog(QDialog):
    """A modal loading dialog that can be used as an async context manager"""
    def __init__(self, parent=None, message="Loading..."):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Loading"))
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        layout = QVBoxLayout(self)
        label = QLabel(self.tr(message))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.resize(200, 100)
    
    async def __aenter__(self):
        self.show()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

class JobDialog(QDialog):
    """Dialog for adding or editing a job"""
    def __init__(self, storage: Storage, job: Job = None, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.job = job
        self.setWindowTitle(self.tr("Edit Job") if job else self.tr("Add Job"))
        self.resize(500, 250)
        
        layout = QFormLayout(self)
        
        # Create input fields
        self.name_input = QLineEdit()
        self.repository_combo = QComboBox()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["backup", "forget", "prune", "check"])
        self.schedule_input = QLineEdit()
        self.directory_input = QLineEdit()
        self.directory_browse_btn = QPushButton(self.tr("Browse..."))
        self.directory_browse_btn.clicked.connect(self.browse_directory)
        self.additional_args_input = QLineEdit()
        self.enabled_checkbox = QCheckBox()
        self.enabled_checkbox.setChecked(True)
        
        # Load repositories into combo box
        repositories = storage.load_repositories()
        if not repositories:
            QMessageBox.warning(self, "No Repositories", "Please add a repository first.")
        
        for repo in repositories:
            self.repository_combo.addItem(repo.name)
        
        # If editing, populate fields
        if job:
            self.name_input.setText(job.name)
            self.name_input.setReadOnly(True)  # Don't allow changing name
            
            # Set repository
            index = self.repository_combo.findText(job.target_repo)
            if index >= 0:
                self.repository_combo.setCurrentIndex(index)
            
            # Set type
            type_index = self.type_combo.findText(job.type)
            if type_index >= 0:
                self.type_combo.setCurrentIndex(type_index)
            
            self.schedule_input.setText(job.schedule)
            self.directory_input.setText(job.directory)
            self.additional_args_input.setText(job.additional_args)
            self.enabled_checkbox.setChecked(job.enabled)
        else:
            # Default schedule example
            self.schedule_input.setPlaceholderText("e.g., 0 2 * * * or interval:1h")
            self.directory_input.setPlaceholderText("/home/user/documents")
            self.additional_args_input.setPlaceholderText("e.g., --exclude-file /path/to/exclude.txt")
        
        # Add fields to form
        layout.addRow(self.tr("Name:"), self.name_input)
        layout.addRow(self.tr("Repository:"), self.repository_combo)
        layout.addRow(self.tr("Type:"), self.type_combo)
        layout.addRow(self.tr("Schedule:"), self.schedule_input)
        
        # Add help text for schedule
        help_label = QLabel(self.tr("Cron format: '0 2 * * *' (2 AM daily)\nInterval: 'interval:1h', 'interval:30m', 'interval:1d'"))
        help_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addRow("", help_label)
        
        # Directory with browse button
        directory_layout = QHBoxLayout()
        directory_layout.addWidget(self.directory_input)
        directory_layout.addWidget(self.directory_browse_btn)
        layout.addRow(self.tr("Directory to Backup:"), directory_layout)
        
        layout.addRow(self.tr("Additional Arguments:"), self.additional_args_input)
        layout.addRow(self.tr("Enabled"), self.enabled_checkbox)
        
        # Add buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def browse_directory(self):
        """Open file dialog to select a directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Directory to Backup"),
            self.directory_input.text() or str(Path.home()),
            QFileDialog.ShowDirsOnly
        )
        if directory:
            self.directory_input.setText(directory)
    
    def get_job(self) -> Job:
        """Get the job data from the dialog"""
        return Job(
            name=self.name_input.text().strip(),
            target_repo=self.repository_combo.currentText(),
            type=self.type_combo.currentText(),
            schedule=self.schedule_input.text().strip(),
            additional_args=self.additional_args_input.text().strip(),
            directory=self.directory_input.text().strip(),
            enabled=self.enabled_checkbox.isChecked()
        )

class RepositoryDialog(QDialog):
    """Dialog for adding or editing a repository"""
    def __init__(self, repository: Repository = None, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle(self.tr("Edit Repository") if repository else self.tr("Add Repository"))
        self.resize(500, 200)
        
        layout = QFormLayout(self)
        
        # Create input fields
        self.name_input = QLineEdit()
        self.url_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        
        # If editing, populate fields
        if repository:
            self.name_input.setText(repository.name)
            self.name_input.setReadOnly(True)  # Don't allow changing name
            self.url_input.setText(repository.url)
            self.password_input.setText(repository.password)
        
        # Add fields to form
        layout.addRow(self.tr("Name:"), self.name_input)
        layout.addRow(self.tr("URL/Path:"), self.url_input)
        layout.addRow(self.tr("Password:"), self.password_input)
        
        # Add buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def get_repository(self) -> Repository:
        """Get the repository data from the dialog"""
        return Repository(
            name=self.name_input.text().strip(),
            url=self.url_input.text().strip(),
            password=self.password_input.text()
        )

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("ResticTray"))
        self.resize(800, 600)
        
        # Set window icon
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Initialize storage
        self.storage = Storage()
        
        # Initialize job scheduler
        self.scheduler = JobScheduler(self.storage, log_callback=self.log)
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Create Dashboard tab
        dashboard_widget = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_widget)
        
        # History section
        history_label = QLabel(self.tr("Recent Backup History:"))
        dashboard_layout.addWidget(history_label)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(10)
        self.history_table.setHorizontalHeaderLabels([
            self.tr("Timestamp"), self.tr("Job"), self.tr("Repository"), self.tr("Status"), self.tr("Files"), self.tr("Size"), self.tr("Duration"), self.tr("Snapshot ID"), self.tr("Summary"), self.tr("Exit Code")
        ])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        dashboard_layout.addWidget(self.history_table)
        
        # Refresh button for history
        refresh_history_btn = QPushButton(self.tr("Refresh History"))
        refresh_history_btn.clicked.connect(self.refresh_history)
        dashboard_layout.addWidget(refresh_history_btn)
        
        # Log section
        log_label = QLabel(self.tr("Activity Log:"))
        dashboard_layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        dashboard_layout.addWidget(self.log_text)
        
        self.tabs.addTab(dashboard_widget, self.tr("Dashboard"))
        
        # Create Repositories tab
        repositories_widget = QWidget()
        repositories_layout = QVBoxLayout(repositories_widget)
        
        # Repository list
        self.repository_list = QListWidget()
        self.repository_list.itemSelectionChanged.connect(self.on_repository_selected)
        repositories_layout.addWidget(QLabel(self.tr("Configured Repositories:")))
        repositories_layout.addWidget(self.repository_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.add_repo_btn = QPushButton(self.tr("Add Repository"))
        self.add_repo_btn.clicked.connect(self.add_repository)
        self.edit_repo_btn = QPushButton(self.tr("Edit Repository"))
        self.edit_repo_btn.clicked.connect(self.edit_repository)
        self.edit_repo_btn.setEnabled(False)
        self.delete_repo_btn = QPushButton(self.tr("Delete Repository"))
        self.delete_repo_btn.clicked.connect(self.delete_repository)
        self.delete_repo_btn.setEnabled(False)
        self.unlock_repo_btn = QPushButton(self.tr("Unlock Repository"))
        self.unlock_repo_btn.clicked.connect(self.unlock_repository)
        self.unlock_repo_btn.setEnabled(False)
        
        button_layout.addWidget(self.add_repo_btn)
        button_layout.addWidget(self.edit_repo_btn)
        button_layout.addWidget(self.delete_repo_btn)
        button_layout.addWidget(self.unlock_repo_btn)
        button_layout.addStretch()
        
        repositories_layout.addLayout(button_layout)
        self.tabs.addTab(repositories_widget, self.tr("Repositories"))
        
        # Create Jobs tab
        jobs_widget = QWidget()
        jobs_layout = QVBoxLayout(jobs_widget)
        
        # Job list
        self.job_list = QListWidget()
        self.job_list.itemSelectionChanged.connect(self.on_job_selected)
        jobs_layout.addWidget(QLabel(self.tr("Scheduled Jobs:")))
        jobs_layout.addWidget(self.job_list)
        
        # Buttons
        job_button_layout = QHBoxLayout()
        self.add_job_btn = QPushButton(self.tr("Add Job"))
        self.add_job_btn.clicked.connect(self.add_job)
        self.edit_job_btn = QPushButton(self.tr("Edit Job"))
        self.edit_job_btn.clicked.connect(self.edit_job)
        self.edit_job_btn.setEnabled(False)
        self.delete_job_btn = QPushButton(self.tr("Delete Job"))
        self.delete_job_btn.clicked.connect(self.delete_job)
        self.delete_job_btn.setEnabled(False)
        self.run_job_btn = QPushButton(self.tr("Run Now"))
        self.run_job_btn.clicked.connect(self.run_job_now)
        self.run_job_btn.setEnabled(False)
        
        job_button_layout.addWidget(self.add_job_btn)
        job_button_layout.addWidget(self.edit_job_btn)
        job_button_layout.addWidget(self.delete_job_btn)
        job_button_layout.addWidget(self.run_job_btn)
        job_button_layout.addStretch()
        
        jobs_layout.addLayout(job_button_layout)
        self.tabs.addTab(jobs_widget, self.tr("Jobs"))
        
        # Create Browse tab
        browse_widget = QWidget()
        browse_layout = QVBoxLayout(browse_widget)
        
        # Repository selection for browsing
        repo_select_layout = QHBoxLayout()
        repo_select_layout.addWidget(QLabel(self.tr("Repository:")))
        self.browse_repo_combo = QComboBox()
        self.browse_repo_combo.currentTextChanged.connect(self.on_browse_repo_changed)
        repo_select_layout.addWidget(self.browse_repo_combo)
        
        self.browse_load_snapshots_btn = QPushButton(self.tr("Load Snapshots"))
        self.browse_load_snapshots_btn.clicked.connect(self.load_snapshots)
        repo_select_layout.addWidget(self.browse_load_snapshots_btn)
        repo_select_layout.addStretch()
        
        browse_layout.addLayout(repo_select_layout)
        
        # Create splitter for snapshots and files
        browse_splitter = QSplitter()
        
        # Snapshots section
        snapshots_widget = QWidget()
        snapshots_layout = QVBoxLayout(snapshots_widget)
        snapshots_layout.setContentsMargins(0, 0, 0, 0)
        
        snapshots_layout.addWidget(QLabel(self.tr("Snapshots:")))
        self.snapshots_table = QTableWidget()
        self.snapshots_table.setColumnCount(5)
        self.snapshots_table.setHorizontalHeaderLabels([
            self.tr("ID"), self.tr("Time"), self.tr("Host"), self.tr("Paths"), self.tr("Tags")
        ])
        self.snapshots_table.horizontalHeader().setStretchLastSection(True)
        self.snapshots_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.snapshots_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.snapshots_table.itemSelectionChanged.connect(self.on_snapshot_selected)
        snapshots_layout.addWidget(self.snapshots_table)
        
        browse_splitter.addWidget(snapshots_widget)
        
        # Files section
        files_widget = QWidget()
        files_layout = QVBoxLayout(files_widget)
        files_layout.setContentsMargins(0, 0, 0, 0)
        
        files_layout.addWidget(QLabel(self.tr("Files in Snapshot:")))
        self.files_tree = QTreeWidget()
        self.files_tree.setHeaderLabels([self.tr("Name"), self.tr("Type"), self.tr("Size")])
        self.files_tree.setColumnWidth(0, 400)
        self.files_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files_tree.customContextMenuRequested.connect(self.show_file_context_menu)
        files_layout.addWidget(self.files_tree)
        
        browse_splitter.addWidget(files_widget)
        
        # Set splitter proportions
        browse_splitter.setSizes([400, 400])
        
        browse_layout.addWidget(browse_splitter)
        
        self.tabs.addTab(browse_widget, self.tr("Browse"))
        
        # Load repositories, jobs, and history
        self.refresh_repositories()
        self.refresh_jobs()
        self.refresh_history()
        self.refresh_browse_repos()
        
        self.log("ResticTray started")
    
    def log(self, message: str):
        """Append a message to the log"""
        self.log_text.append(message)
    
    def start_scheduler(self):
        """Start the job scheduler"""
        self.scheduler.load_and_schedule_all_jobs()
        self.scheduler.start()
    
    def stop_scheduler(self):
        """Stop the job scheduler"""
        self.scheduler.shutdown()
    
    def refresh_repositories(self):
        """Refresh the repository list"""
        self.repository_list.clear()
        repositories = self.storage.load_repositories()
        for repo in repositories:
            self.repository_list.addItem(f"{repo.name} ({repo.url})")
    
    def on_repository_selected(self):
        """Enable/disable edit and delete buttons based on selection"""
        has_selection = len(self.repository_list.selectedItems()) > 0
        self.edit_repo_btn.setEnabled(has_selection)
        self.delete_repo_btn.setEnabled(has_selection)
        self.unlock_repo_btn.setEnabled(has_selection)
    
    def add_repository(self):
        """Open dialog to add a new repository"""
        dialog = RepositoryDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            repo = dialog.get_repository()
            if not repo.name or not repo.url:
                QMessageBox.warning(self, self.tr("Invalid Input"), self.tr("Name and URL are required."))
                return
            
            if self.storage.add_repository(repo):
                self.refresh_repositories()
                self.refresh_browse_repos()
                self.log(self.tr("Added repository: %1").replace("%1", repo.name))
            else:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Repository '%1' already exists.").replace("%1", repo.name))
    
    def edit_repository(self):
        """Open dialog to edit selected repository"""
        selected_items = self.repository_list.selectedItems()
        if not selected_items:
            return
        
        # Extract repository name from list item text
        item_text = selected_items[0].text()
        repo_name = item_text.split(" (")[0]
        
        repo = self.storage.get_repository(repo_name)
        if not repo:
            return
        
        dialog = RepositoryDialog(repository=repo, parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated_repo = dialog.get_repository()
            if self.storage.update_repository(repo_name, updated_repo):
                self.refresh_repositories()
                self.refresh_browse_repos()
                self.log(self.tr("Updated repository: %1").replace("%1", repo_name))
    
    def delete_repository(self):
        """Delete selected repository"""
        selected_items = self.repository_list.selectedItems()
        if not selected_items:
            return
        
        # Extract repository name from list item text
        item_text = selected_items[0].text()
        repo_name = item_text.split(" (")[0]
        
        reply = QMessageBox.question(
            self, 
            self.tr("Confirm Delete"),
            self.tr("Are you sure you want to delete repository '%1'?").replace("%1", repo_name),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.storage.delete_repository(repo_name):
                self.refresh_repositories()
                self.refresh_browse_repos()
                self.log(self.tr("Deleted repository: %1").replace("%1", repo_name))
    
    def unlock_repository(self):
        """Unlock selected repository"""
        selected_items = self.repository_list.selectedItems()
        if not selected_items:
            return
        
        # Extract repository name from list item text
        item_text = selected_items[0].text()
        repo_name = item_text.split(" (")[0]
        
        repo = self.storage.get_repository(repo_name)
        if not repo:
            return
        
        reply = QMessageBox.question(
            self, 
            self.tr("Confirm Unlock"),
            self.tr("Are you sure you want to unlock repository '%1'?\n\nThis will remove stale locks.").replace("%1", repo_name),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log(self.tr("Unlocking repository: %1...").replace("%1", repo_name))
            asyncio.create_task(self._unlock_repository_async(repo))
    
    async def _unlock_repository_async(self, repository: Repository):
        """Async task to unlock repository"""
        try:
            process = await asyncio.create_subprocess_exec(
                'restic',
                '-r', repository.url,
                '--password-command', f"echo '{repository.password}'",
                'unlock',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.log(self.tr("Repository '%1' unlocked successfully").replace("%1", repository.name))
                QMessageBox.information(
                    self,
                    self.tr("Success"),
                    self.tr("Repository '%1' has been unlocked.").replace("%1", repository.name)
                )
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                self.log(self.tr("Failed to unlock repository '%1': %2").replace("%1", repository.name).replace("%2", error_msg))
                QMessageBox.warning(
                    self,
                    self.tr("Unlock Failed"),
                    self.tr("Failed to unlock repository '%1'.\n\n%2").replace("%1", repository.name).replace("%2", error_msg)
                )
        except Exception as e:
            self.log(self.tr("Error unlocking repository '%1': %2").replace("%1", repository.name).replace("%2", str(e)))
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("An error occurred while unlocking the repository:\n%1").replace("%1", str(e))
            )
    
    # Job management methods
    def refresh_jobs(self):
        """Refresh the job list"""
        self.job_list.clear()
        jobs = self.storage.load_jobs()
        for job in jobs:
            status = "✓" if job.enabled else "✗"
            self.job_list.addItem(f"{status} {job.name} - {job.target_repo} [{job.type}] ({job.schedule})")
    
    def refresh_browse_repos(self):
        """Refresh the repository combo box in Browse tab"""
        self.browse_repo_combo.clear()
        repositories = self.storage.load_repositories()
        for repo in repositories:
            self.browse_repo_combo.addItem(repo.name)
    
    def on_browse_repo_changed(self):
        """Handle repository selection change in Browse tab"""
        # Clear snapshots and files when repository changes
        self.snapshots_table.setRowCount(0)
        self.files_tree.clear()
    
    def on_snapshot_selected(self):
        """Handle snapshot selection change"""
        selected_items = self.snapshots_table.selectedItems()
        if not selected_items:
            self.files_tree.clear()
            return
        
        # Get the selected snapshot ID from the first column
        row = self.snapshots_table.currentRow()
        if row < 0:
            return
        
        snapshot_id_item = self.snapshots_table.item(row, 0)
        if not snapshot_id_item:
            return
        
        snapshot_id = snapshot_id_item.text()
        repo_name = self.browse_repo_combo.currentText()
        
        if not repo_name or not snapshot_id:
            return
        
        repo = self.storage.get_repository(repo_name)
        if not repo:
            return
        
        self.log(self.tr("Loading files for snapshot %1...").replace("%1", snapshot_id))
        asyncio.create_task(self._load_snapshot_files_async(repo, snapshot_id))
    
    def load_snapshots(self):
        """Load snapshots for the selected repository"""
        repo_name = self.browse_repo_combo.currentText()
        if not repo_name:
            QMessageBox.warning(self, self.tr("No Repository"), self.tr("Please select a repository first."))
            return
        
        repo = self.storage.get_repository(repo_name)
        if not repo:
            return
        
        self.log(self.tr("Loading snapshots for repository: %1...").replace("%1", repo_name))
        asyncio.create_task(self._load_snapshots_async(repo))
    
    async def _load_snapshots_async(self, repository: Repository):
        """Async task to load snapshots"""
        async with LoadingDialog(self, "Loading..."):
            try:
                process = await asyncio.create_subprocess_exec(
                    'restic',
                    '-r', repository.url,
                    '--password-command', f"echo '{repository.password}'",
                    '--json',
                    'snapshots',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    snapshots = json.loads(stdout.decode())
                    self._display_snapshots(snapshots)
                    self.log(self.tr("Loaded %1 snapshots").replace("%1", str(len(snapshots))))
                else:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    self.log(self.tr("Failed to load snapshots: %1").replace("%1", error_msg))
                    QMessageBox.warning(
                        self,
                        self.tr("Snapshots Load Failed"),
                        self.tr("Failed to load snapshots.\n\n%1").replace("%1", error_msg)
                    )
            except Exception as e:
                self.log(self.tr("Error loading snapshots: %1").replace("%1", str(e)))
                QMessageBox.warning(
                    self,
                    self.tr("Error"),
                    self.tr("An error occurred while loading snapshots:\n%1").replace("%1", str(e))
                )
    
    def _display_snapshots(self, snapshots: list):
        """Display snapshots in the table"""
        self.snapshots_table.setRowCount(0)
        
        for snapshot in snapshots:
            row_position = self.snapshots_table.rowCount()
            self.snapshots_table.insertRow(row_position)
            
            # Snapshot ID (short)
            snapshot_id = snapshot.get('short_id', snapshot.get('id', '')[:8])
            self.snapshots_table.setItem(row_position, 0, QTableWidgetItem(snapshot_id))
            
            # Time
            time = snapshot.get('time', '')
            self.snapshots_table.setItem(row_position, 1, QTableWidgetItem(time))
            
            # Host
            host = snapshot.get('hostname', '')
            self.snapshots_table.setItem(row_position, 2, QTableWidgetItem(host))
            
            # Paths
            paths = ', '.join(snapshot.get('paths', []))
            self.snapshots_table.setItem(row_position, 3, QTableWidgetItem(paths))
            
            # Tags
            tags = ', '.join(snapshot.get('tags', []))
            self.snapshots_table.setItem(row_position, 4, QTableWidgetItem(tags))
        
        self.snapshots_table.resizeColumnsToContents()
    
    async def _load_snapshot_files_async(self, repository: Repository, snapshot_id: str):
        """Async task to load files from a snapshot"""
        async with LoadingDialog(self, "Loading..."):
            try:
                process = await asyncio.create_subprocess_exec(
                    'restic',
                    '-r', repository.url,
                    '--password-command', f"echo '{repository.password}'",
                    'ls',
                    snapshot_id,
                    '--json',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    files_data = stdout.decode()
                    # Parse JSON lines
                    files = []
                    for line in files_data.strip().split('\n'):
                        if line:
                            try:
                                files.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                    
                    self.log(self.tr("Loaded files for snapshot %1").replace("%1", snapshot_id))
                    self._display_files(files)
                else:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    self.log(self.tr("Failed to load snapshot files: %1").replace("%1", error_msg))
                    QMessageBox.warning(
                        self,
                        self.tr("Snapshot Files Load Failed"),
                        self.tr("Failed to load snapshot files.\n\n%1").replace("%1", error_msg)
                    )
            except Exception as e:
                self.log(self.tr("Error loading snapshot files: %1").replace("%1", str(e)))
                QMessageBox.warning(
                    self,
                    self.tr("Error"),
                    self.tr("An error occurred while loading snapshot files:\n%1").replace("%1", str(e))
                )
    
    def _display_files(self, files: list):
        """Display files in the tree widget"""
        self.files_tree.clear()
        
        # Create a dictionary to track directories
        dir_items = {}
        
        for file_info in files:
            if file_info.get('struct_type') != 'node':
                continue
            
            path = file_info.get('path', '')
            if not path:
                continue
            
            node_type = file_info.get('type', '')
            size = file_info.get('size', 0)
            
            # Determine display values
            file_type = self.tr("Directory") if node_type == 'dir' else "File"
            size_str = str(size) if node_type != 'dir' else ""
            
            # Split path into parts
            path_parts = path.strip('/').split('/')
            if not path_parts or path_parts == ['']:
                continue
            
            # Build the tree structure
            parent_item = None
            current_path = ""
            
            for i, part in enumerate(path_parts):
                if not part:
                    continue
                    
                current_path = '/'.join(path_parts[:i+1])
                
                # Check if this path already exists
                if current_path in dir_items:
                    parent_item = dir_items[current_path]
                else:
                    # Create new item
                    if parent_item is None:
                        item = QTreeWidgetItem(self.files_tree)
                    else:
                        item = QTreeWidgetItem(parent_item)
                    
                    item.setText(0, part)
                    
                    # Set type and size only for the last part (actual file/dir)
                    if i == len(path_parts) - 1:
                        item.setText(1, file_type)
                        if size_str:
                            # Format size in human readable format
                            size_mb = size / (1024 * 1024)
                            if size_mb >= 1024:
                                size_display = f"{size_mb / 1024:.2f} GB"
                            elif size_mb >= 1:
                                size_display = f"{size_mb:.2f} MB"
                            else:
                                size_display = f"{size / 1024:.2f} KB"
                            item.setText(2, size_display)
                    else:
                        item.setText(1, "Directory")
                    
                    dir_items[current_path] = item
                    parent_item = item
        
        self.files_tree.expandToDepth(1)
    
    def show_file_context_menu(self, position):
        """Show context menu for file tree"""
        item = self.files_tree.itemAt(position)
        if not item:
            return
        
        menu = QMenu()
        restore_action = QAction(self.tr("Restore"), self)
        restore_action.triggered.connect(lambda: self.restore_file(item))
        menu.addAction(restore_action)
        
        menu.exec(self.files_tree.viewport().mapToGlobal(position))
    
    def restore_file(self, item: QTreeWidgetItem):
        """Restore the selected file or folder"""
        # Get the full path by traversing up the tree
        path_parts = []
        current = item
        while current:
            path_parts.insert(0, current.text(0))
            current = current.parent()
        
        file_path = '/' + '/'.join(path_parts)
        
        # Get selected snapshot
        selected_row = self.snapshots_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "No Snapshot", "Please select a snapshot first.")
            return
        
        snapshot_id_item = self.snapshots_table.item(selected_row, 0)
        if not snapshot_id_item:
            return
        
        snapshot_id = snapshot_id_item.text()
        repo_name = self.browse_repo_combo.currentText()
        
        if not repo_name:
            return
        
        repo = self.storage.get_repository(repo_name)
        if not repo:
            return
        
        # Ask user for restore location
        restore_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Restore Location"),
            str(Path.home()),
            QFileDialog.ShowDirsOnly
        )
        
        if not restore_dir:
            return
        
        reply = QMessageBox.question(
            self,
            self.tr("Confirm Restore"),
            self.tr("Restore '%1' from snapshot %2 to:\n%3\n\nThis will overwrite existing files with the same name.").replace("%1", file_path).replace("%2", snapshot_id).replace("%3", restore_dir),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log(self.tr("Restoring '%1' from snapshot %2 to %3...").replace("%1", file_path).replace("%2", snapshot_id).replace("%3", restore_dir))
            asyncio.create_task(self._restore_file_async(repo, snapshot_id, file_path, restore_dir))
    
    async def _restore_file_async(self, repository: Repository, snapshot_id: str, file_path: str, restore_dir: str):
        """Async task to restore a file or folder"""
        async with LoadingDialog(self, "Restoring..."):
            try:
                process = await asyncio.create_subprocess_exec(
                    'restic',
                    '-r', repository.url,
                    '--password-command', f"echo '{repository.password}'",
                    'restore',
                    snapshot_id,
                    '--target', restore_dir,
                    '--include', file_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    self.log(self.tr("Successfully restored '%1' to %2").replace("%1", file_path).replace("%2", restore_dir))
                    QMessageBox.information(
                        self,
                        self.tr("Restore Successful"),
                        self.tr("File(s) restored successfully to:\n%1").replace("%1", restore_dir)
                    )
                else:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    self.log(self.tr("Failed to restore file: %1").replace("%1", error_msg))
                    QMessageBox.warning(
                        self,
                        self.tr("Restore Failed"),
                        self.tr("Failed to restore file(s).\n\n%1").replace("%1", error_msg)
                    )
            except Exception as e:
                self.log(self.tr("Error restoring file: %1").replace("%1", str(e)))
                QMessageBox.warning(
                    self,
                    self.tr("Error"),
                    self.tr("An error occurred while restoring:\n%1").replace("%1", str(e))
                )
    
    def refresh_history(self):
        """Refresh the history table"""
        self.history_table.setRowCount(0)
        history_entries = self.storage.get_latest_history(limit=50)
        
        for entry in history_entries:
            row_position = self.history_table.rowCount()
            self.history_table.insertRow(row_position)
            
            # Set row background color based on success/failure
            bg_color = QColor(200, 255, 200) if entry.success else QColor(255, 200, 200)  # Light green or light red
            
            # Timestamp
            timestamp_item = QTableWidgetItem(entry.timestamp)
            timestamp_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 0, timestamp_item)
            
            # Job name
            job_item = QTableWidgetItem(entry.job_name)
            job_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 1, job_item)
            
            # Repository name
            repo_item = QTableWidgetItem(entry.repo_name)
            repo_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 2, repo_item)
            
            # Status
            status_text = self.tr("✓ Success") if entry.success else self.tr("✗ Failed")
            status_item = QTableWidgetItem(status_text)
            status_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 3, status_item)
            
            # Files
            files_item = QTableWidgetItem(str(entry.files))
            files_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 4, files_item)
            
            # Size (formatted)
            size_mb = entry.bytes / (1024 * 1024)
            if size_mb >= 1024:
                size_str = f"{size_mb / 1024:.2f} GB"
            else:
                size_str = f"{size_mb:.2f} MB"
            size_item = QTableWidgetItem(size_str)
            size_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 5, size_item)
            
            # Duration (formatted)
            minutes = entry.duration // 60
            seconds = entry.duration % 60
            if minutes > 0:
                duration_str = f"{minutes}m {seconds}s"
            else:
                duration_str = f"{seconds}s"
            duration_item = QTableWidgetItem(duration_str)
            duration_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 6, duration_item)
            
            # Snapshot ID
            snapshot_id = entry.snapshot_id if entry.snapshot_id else "N/A"
            snapshot_item = QTableWidgetItem(snapshot_id)
            snapshot_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 7, snapshot_item)
            
            # Summary text
            summary = entry.summary_text if hasattr(entry, 'summary_text') else ""
            summary_item = QTableWidgetItem(summary)
            summary_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 8, summary_item)
            
            # Exit code
            exit_code = str(entry.exit_code) if hasattr(entry, 'exit_code') else "0"
            exit_code_item = QTableWidgetItem(exit_code)
            exit_code_item.setBackground(bg_color)
            self.history_table.setItem(row_position, 9, exit_code_item)
        
        # Resize columns to content
        self.history_table.resizeColumnsToContents()
    
    def on_job_selected(self):
        """Enable/disable job buttons based on selection"""
        has_selection = len(self.job_list.selectedItems()) > 0
        self.edit_job_btn.setEnabled(has_selection)
        self.delete_job_btn.setEnabled(has_selection)
        self.run_job_btn.setEnabled(has_selection)
    
    def add_job(self):
        """Open dialog to add a new job"""
        dialog = JobDialog(self.storage, parent=self)
        if dialog.exec() == QDialog.Accepted:
            job = dialog.get_job()
            if not job.name or not job.schedule:
                QMessageBox.warning(self, self.tr("Invalid Input"), self.tr("Name and URL are required."))
                return
            
            if self.storage.add_job(job):
                self.refresh_jobs()
                self.scheduler.add_job(job)
                self.log(self.tr("Added job: %1").replace("%1", job.name))
            else:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Job '%1' already exists.").replace("%1", job.name))
    
    def edit_job(self):
        """Open dialog to edit selected job"""
        selected_items = self.job_list.selectedItems()
        if not selected_items:
            return
        
        # Extract job name from list item text
        item_text = selected_items[0].text()
        # Remove status symbol and parse name
        job_name = item_text.split(" ", 1)[1].split(" - ")[0]
        
        job = self.storage.get_job(job_name)
        if not job:
            return
        
        dialog = JobDialog(self.storage, job=job, parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated_job = dialog.get_job()
            if self.storage.update_job(job_name, updated_job):
                self.refresh_jobs()
                # Update scheduler
                self.scheduler.remove_job(job_name)
                self.scheduler.add_job(updated_job)
                self.log(self.tr("Updated job: %1").replace("%1", job_name))
    
    def delete_job(self):
        """Delete selected job"""
        selected_items = self.job_list.selectedItems()
        if not selected_items:
            return
        
        # Extract job name from list item text
        item_text = selected_items[0].text()
        job_name = item_text.split(" ", 1)[1].split(" - ")[0]
        
        reply = QMessageBox.question(
            self, 
            self.tr("Confirm Delete"),
            self.tr("Are you sure you want to delete job '%1'?").replace("%1", job_name),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.storage.delete_job(job_name):
                self.refresh_jobs()
                self.scheduler.remove_job(job_name)
                self.log(self.tr("Deleted job: %1").replace("%1", job_name))
    
    def run_job_now(self):
        """Manually trigger selected job to run immediately"""
        selected_items = self.job_list.selectedItems()
        if not selected_items:
            return
        
        # Extract job name from list item text
        item_text = selected_items[0].text()
        job_name = item_text.split(" ", 1)[1].split(" - ")[0]
        
        job = self.storage.get_job(job_name)
        if not job:
            return
        
        # Run the job asynchronously
        asyncio.create_task(self.scheduler.run_backup_job(job))
        self.log(self.tr("Manually triggered job: %1").replace("%1", job_name))
    
    def closeEvent(self, event):
        """Override close event to hide instead of quit"""
        event.ignore()
        self.hide()

class TrayIcon(QSystemTrayIcon):
    def __init__(self, icon, backup_icon, main_window, parent=None):
        super().__init__(icon, parent)
        self.normal_icon = icon
        self.backup_icon = backup_icon
        self.main_window = main_window
        
        # Create menu
        menu = QMenu()
        
        show_window_action = QAction(QCoreApplication.translate("TrayIcon", "Show Window"), self)
        show_window_action.triggered.connect(self.toggle_window)
        menu.addAction(show_window_action)
        
        menu.addSeparator()
        
        quit_action = QAction(QCoreApplication.translate("TrayIcon", "Quit"), self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        
        # Set the context menu
        self.setContextMenu(menu)
        
        # Connect double-click event
        self.activated.connect(self.on_tray_icon_activated)
        
        # Set initial tooltip
        self.setToolTip(QCoreApplication.translate("TrayIcon", "ResticTray - Idle"))
        
        # Show a welcome message
        self.showMessage(
            QCoreApplication.translate("TrayIcon", "ResticTray"),
            QCoreApplication.translate("TrayIcon", "Application started and running in tray (asyncio enabled)"),
            QSystemTrayIcon.Information,
            2000
        )

        self._quit_task: asyncio.Task|None = None
    
    def quit(self):
        if self._quit_task is None:
            self._quit_task = asyncio.create_task(self._quit_async())

    async def _quit_async(self):
        print("Waiting for running jobs to finish...")
        for lock in globals.repo_locks.values():
            await lock.acquire()
        QApplication.quit()
    
    def state_update_callback(self, message: str):
        self.setToolTip(QCoreApplication.translate("TrayIcon", "ResticTray - %1").replace("%1", message))

    def toggle_window(self):
        """Show or hide the main window"""
        if self.main_window.isVisible():
            self.main_window.hide()
        else:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
    
    def show_message(self):
        self.showMessage(
            QCoreApplication.translate("TrayIcon", "ResticTray"),
            QCoreApplication.translate("TrayIcon", "This is a system tray notification!"),
            QSystemTrayIcon.Information,
            2000
        )
    
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.toggle_window()

async def main_async():
    app = QApplication(sys.argv)
    
    # Set up translations
    translator = QTranslator()
    
    # Get the locale - check LANG environment variable first, then system locale
    import os
    env_lang = os.environ.get('LANG', '')
    if env_lang:
        # Extract locale from LANG (e.g., 'de_DE.UTF-8' -> 'de_DE')
        system_locale = env_lang.split('.')[0]
    else:
        # Fallback to Qt's system locale detection
        system_locale = QLocale.system().name()
    
    # Build path to translation file
    translations_dir = Path(__file__).parent / "translations"
    translation_file = translations_dir / f"restictray_{system_locale}.qm"
    
    # Try to load the specific locale first (e.g., de_DE)
    if not translation_file.exists():
        # Try the language without country code (e.g., de)
        language_code = system_locale.split('_')[0]
        translation_file = translations_dir / f"restictray_{language_code}.qm"
    
    if translation_file.exists():
        if translator.load(str(translation_file)):
            app.installTranslator(translator)
            print(f"Loaded translation: {translation_file.name}")
        else:
            print(f"Failed to load translation: {translation_file.name}")
    else:
        print(f"No translation found for locale: {system_locale}")
        print(f"Using default language (English)")
    
    # Set up the asyncio event loop with qasync
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Check if system tray is available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this system")
        sys.exit(1)
    
    # Prevent app from quitting when last window is closed
    app.setQuitOnLastWindowClosed(False)
    
    # Load custom icon if available
    icon_path = Path(__file__).parent / "icon.png"
    if icon_path.exists():
        custom_icon = QIcon(str(icon_path))
        app.setWindowIcon(custom_icon)
    
    # Create icons from built-in styles or use custom icon
    if icon_path.exists():
        normal_icon = QIcon(str(icon_path))
    else:
        normal_icon = app.style().standardIcon(app.style().StandardPixmap.SP_DriveHDIcon)
    backup_icon = app.style().standardIcon(app.style().StandardPixmap.SP_ArrowUp)
    
    # Create main window (hidden by default)
    main_window = MainWindow()
    globals.main_window = main_window  # Set global reference
    
    # Create and show tray icon
    tray_icon = TrayIcon(normal_icon, backup_icon, main_window)
    globals.tray_icon = tray_icon  # Set global reference
    tray_icon.show()
    
    # Start the job scheduler
    main_window.scheduler.scheduler._eventloop = loop
    main_window.start_scheduler()
    
    # Run the asyncio event loop
    with loop:
        try:
            loop.run_forever()
        finally:
            main_window.stop_scheduler()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()