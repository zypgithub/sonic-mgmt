from dataclasses import dataclass
from .Connect_to_MSSQL import ConnectMSSQL
from datetime import datetime
import logging
logger = logging.getLogger()


class MarsRespondDB(ConnectMSSQL):
    def __init__(self, server, database, username, password):
        ConnectMSSQL.__init__(self, server, database, username, password)
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.cursor = None
        self.conn = None
        self.session_id = 0
        self.is_connected = False
        self.columns = self.get_table_column_names('mars_respond')
        self.keys_not_in_mars_respond = ["log_analyzer_redmine_issues"]

    def write_json_to_db(self, mars_data_list):
        if not self.is_connected:
            self.connect_db()

        for row in mars_data_list:
            for key in row:
                if key in self.keys_not_in_mars_respond:
                    # these keys are not in the mars_respond table
                    continue
                if key not in self.columns:
                    logger.warning(
                        f"Column {key} is not found in the database. Skipping this key.")
            self.insert_row(row)
        self.disconnect_db()

    def _escape_sql_string(self, value):
        """Escape single quotes for SQL Server ('' is the escape for ')."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    def insert_row(self, row):
        columns_string = ""
        values_string = ""
        for column in self.columns:
            if column == "mars_respond_id":
                # mars_respond_id is the primary key
                continue
            value = row.get(column, '')
            columns_string += f"[{column}], "
            if column == "session_id":
                # session_id is an int
                values_string += f"{value}, "
            else:
                # all the other fields are varchar; escape single quotes for SQL
                values_string += f"'{self._escape_sql_string(value)}', "
        columns_string = columns_string.rstrip(", ")
        values_string = values_string.rstrip(", ")

        insert_query = f"INSERT INTO [dbo].[mars_respond] ({columns_string}) OUTPUT inserted.mars_respond_id VALUES ({values_string})"
        logger.info('Inserting: {} to MARS SQL DB'.format(insert_query))
        try:
            la_table_id = self.query_insert_return_la_table_id(insert_query)
            for la_issue in row.get("log_analyzer_redmine_issues", []):
                insert_la_issue = r"INSERT INTO [dbo].[log_analyzer_redmine_issues]([mars_respond_id], " \
                                  r"[log_analyzer_redmine_issue]) VALUES (" + str(la_table_id) + ", " + \
                                  str(la_issue) + ")"
                logger.info('Inserting: {} to MARS SQL LA Table'.format(insert_la_issue))
                self.query_insert(insert_la_issue)
        except Exception as e:
            logger.error(e)
            raise Exception(e)

    def clear_db(self):
        if self.conn is None:
            self.connect_db()

        clear_cmd = 'truncate table [' + self.database + '].[dbo].[mars_respond]'
        self.execute_db_cmd(clear_cmd)
        self.disconnect_db()
