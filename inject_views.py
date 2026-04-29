import re

html_path = r'c:\Users\sagar\Downloads\mock-interview\forenten\admin.html'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

views = '''
                <!-- NEW VIEWS -->
                <!-- VIEW: SCHEDULING -->
                <div id="view-scheduling" class="view-panel hidden">
                    <div class="section-card">
                        <div class="section-header">
                            <div class="header-icon green"><i class="fas fa-calendar-alt"></i></div>
                            <div>
                                <h3>Interview Scheduling</h3>
                                <p>Manage your upcoming interview calendar and availability</p>
                            </div>
                        </div>
                        <div style="text-align: center; padding: 4rem;">
                            <i class="fas fa-hammer" style="font-size: 3rem; color: var(--border); margin-bottom: 1rem;"></i>
                            <h4 style="color: var(--text-primary); margin-bottom: 0.5rem;">Scheduling Interface</h4>
                            <p style="color: var(--text-muted);">This tab is ready for development. Calendar and booking logic will appear here.</p>
                        </div>
                    </div>
                </div>

                <!-- VIEW: INVITATIONS -->
                <div id="view-invitations" class="view-panel hidden">
                    <div class="section-card">
                        <div class="section-header">
                            <div class="header-icon blue"><i class="fas fa-envelope"></i></div>
                            <div>
                                <h3>Email Invitations</h3>
                                <p>Track sent invites, open rates, and follow-ups</p>
                            </div>
                        </div>
                        <div style="text-align: center; padding: 4rem;">
                            <i class="fas fa-paper-plane" style="font-size: 3rem; color: var(--border); margin-bottom: 1rem;"></i>
                            <h4 style="color: var(--text-primary); margin-bottom: 0.5rem;">Invitation Management</h4>
                            <p style="color: var(--text-muted);">This tab is ready for development. Bulk email logs and stats will appear here.</p>
                        </div>
                    </div>
                </div>

                <!-- VIEW: EVALUATION -->
                <div id="view-evaluation" class="view-panel hidden">
                    <div class="section-card">
                        <div class="section-header">
                            <div class="header-icon purple"><i class="fas fa-clipboard-check"></i></div>
                            <div>
                                <h3>Candidate Evaluation</h3>
                                <p>Score rubrics and in-depth candidate performance reviews</p>
                            </div>
                        </div>
                        <div style="text-align: center; padding: 4rem;">
                            <i class="fas fa-tasks" style="font-size: 3rem; color: var(--border); margin-bottom: 1rem;"></i>
                            <h4 style="color: var(--text-primary); margin-bottom: 0.5rem;">Evaluation Rubrics</h4>
                            <p style="color: var(--text-muted);">This tab is ready for development. Detailed AI scoring matrices will appear here.</p>
                        </div>
                    </div>
                </div>

                <!-- VIEW: REPORTS -->
                <div id="view-reports" class="view-panel hidden">
                    <div class="section-card">
                        <div class="section-header">
                            <div class="header-icon orange"><i class="fas fa-file-invoice"></i></div>
                            <div>
                                <h3>Analytics & Reports</h3>
                                <p>Export hiring data, demographics, and completion metrics</p>
                            </div>
                        </div>
                        <div style="text-align: center; padding: 4rem;">
                            <i class="fas fa-chart-pie" style="font-size: 3rem; color: var(--border); margin-bottom: 1rem;"></i>
                            <h4 style="color: var(--text-primary); margin-bottom: 0.5rem;">Exportable Reports</h4>
                            <p style="color: var(--text-muted);">This tab is ready for development. PDF/Excel downloads and BI charts will appear here.</p>
                        </div>
                    </div>
                </div>
                <!-- END NEW VIEWS -->
'''

target = '<!-- END VIEW: RESULTS -->'
if target in html and 'id="view-scheduling"' not in html:
    html = html.replace(target, target + '\n' + views)
elif '<!-- END VIEW: SETTINGS -->' in html and 'id="view-scheduling"' not in html:
    html = html.replace('<!-- END VIEW: SETTINGS -->', '<!-- END VIEW: SETTINGS -->\n' + views)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
